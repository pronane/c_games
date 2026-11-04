// Arena FC - Godot-free online match loop for the C# desktop client.
//
// The server owns the simulation.  This class:
//   * samples the local pad every physics frame and sends ONLY quantised input;
//   * predicts locally with RollbackPredictor so the ring responds at zero RTT;
//   * keeps a mirror engine holding the authoritative 20 Hz snapshots;
//   * reconciles against each snapshot's tick / RNG word / trailing input log.
// GameApp/MatchView only have to provide the local PlayerCommand and render
// `Engine`; nothing here references Godot, so the core suite can exercise it.
using System;
using System.Collections.Generic;
using ArenaFC.Core;

namespace ArenaFC.Core.Net;

public sealed class OnlineMatch
{
    public readonly OnlineClient Client = new();
    public MatchOptions Options = new();
    public MatchEngine Mirror = null!;
    public RollbackPredictor? Predictor;

    /// <summary>Engine used by the renderer.  Stays the same object across rollbacks.</summary>
    public MatchEngine Engine => Predictor?.Engine ?? Mirror;

    public bool Started;
    public int LocalIndex = -1;
    public int LatestTick;
    public float LastError;
    public int LastReplayed;
    public int Corrections;
    public string Status => Client.Status;
    public int BufferedFrames => Predictor?.BufferedFrames ?? 0;

    public OnlineMatch(MatchOptions? options = null)
    {
        Options = options ?? new MatchOptions();
        Mirror = new MatchEngine(Options);
        Client.PacketReceived += OnPacket;
    }

    public bool Connect(string url, string room, string name, string? token = null,
                        bool create = false, INetTransport? transport = null) =>
        Client.Connect(url, room, name, token, create, transport);

    /// <summary>Called once per physics frame with the freshly sampled local input.</summary>
    public void Step(float dt, PlayerCommand cmd)
    {
        Client.Poll();
        if (!Started || Predictor == null) return;
        int idx = LocalIndex >= 0 ? LocalIndex : Client.LocalPlayerIndex(Mirror.State.Controlled);
        if (idx < 0 || idx >= Mirror.State.Players.Length) idx = Mirror.State.Controlled;
        Client.SendInput(cmd);
        Predictor.Predict(new Dictionary<int, PlayerCommand> { [idx] = cmd });
    }

    private void OnPacket(Packet p)
    {
        switch (p.T)
        {
            case NetProtocol.Begin:
            case NetProtocol.Resume:
                Setup(p);
                break;
            case NetProtocol.Snap:
                OnSnapshot(p);
                break;
            case NetProtocol.End:
                Started = false;
                break;
        }
    }

    private void Setup(Packet p)
    {
        Options = new MatchOptions
        {
            Seed = p.Seed ?? Options.Seed,
            TeamSize = p.Size ?? Options.TeamSize,
            TimeSpeed = p.TimeSpeed ?? Options.TimeSpeed,
            HalfMinutes = p.HalfMinutes ?? Options.HalfMinutes,
            Difficulty = p.Difficulty ?? Options.Difficulty,
            HomeClub = p.HomeClub ?? Options.HomeClub,
            AwayClub = p.AwayClub ?? Options.AwayClub,
            HomeFormation = p.HomeFormation ?? Options.HomeFormation,
            AwayFormation = p.AwayFormation ?? Options.AwayFormation,
            CameraMode = p.CameraMode ?? 0,
            CameraZoom = p.CameraZoom ?? .68f,
            AwayHuman = p.AwayHuman ?? true,
        };
        if (Options.TeamSize is not (5 or 7 or 11)) Options.TeamSize = 5;
        Mirror = new MatchEngine(Options);
        if (p.Full != null) StateCodec.ApplyFull(Mirror, p.Full);
        if (p.Players != null) Snapshot.ApplyImmediate(Mirror, p);
        Predictor = new RollbackPredictor(Options);
        Predictor.HardReset(Mirror, p.Tick ?? 0);
        LocalIndex = Client.LocalPlayerIndex(Mirror.State.Controlled);
        Started = true;
        LatestTick = p.Tick ?? 0;
    }

    private void OnSnapshot(Packet p)
    {
        if (!Started) { Setup(p); return; }
        LatestTick = p.Tick ?? LatestTick;
        if (p.Ctrls != null) LocalIndex = Client.LocalPlayerIndex(Mirror.State.Controlled);

        // Authoritative mirror: the compact wire snapshot is enough for the
        // renderer fields; the predictor's own checkpoints keep every internal
        // timer, so no full-state transfer is needed every 50 ms.
        Snapshot.ApplyImmediate(Mirror, p);
        if (Predictor != null && p.Rng.HasValue && p.Gt.HasValue)
        {
            var inputs = new Dictionary<int, Dictionary<int, PlayerCommand>>();
            if (p.Inputs != null)
                foreach (var f in p.Inputs)
                {
                    var cmds = new Dictionary<int, PlayerCommand>();
                    foreach (var kv in f.C) cmds[kv.Key] = kv.Value.To();
                    inputs[f.T] = cmds;
                }
            var res = Predictor.Reconcile(p.Tick ?? LatestTick, Mirror.State, p.Rng.Value,
                                          p.Gt.Value, inputs, LocalIndex);
            if (res.Applied)
            {
                LastError = res.Error;
                LastReplayed = res.Replayed;
                Corrections = Predictor.Corrections;
            }
        }
    }

    /// <summary>Blend two buffered snapshots into a scratch mirror (browser-style
    /// interpolation, also used by the HUD replay buffer).</summary>
    public static void Interpolate(MatchEngine target, Packet a, Packet b, float t) =>
        Snapshot.ApplyInterpolated(target, a, b, t);

    public void Close()
    {
        Client.Close();
        Started = false;
    }
}
