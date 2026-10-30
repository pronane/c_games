using System;
using MarioKart64.Core;

namespace MarioKart64.Audio
{
    public enum MusicTrackId
    {
        None = 0,
        TitleGroove = 1,
        MenuSetup = 2,
        RacewayCircuit = 3,
        FarmAndBeach = 4,
        DesertAndHighway = 5,
        SnowAndIce = 6,
        CastleAndSpooky = 7,
        RainbowRoad = 8,
        StarmanLoop = 9,
        VictoryPodium = 10,
        BattleArena = 11
    }

    public enum SfxId
    {
        MenuMove = 0,
        MenuConfirm = 1,
        MenuBack = 2,
        CountdownTick = 3,
        CountdownGo = 4,
        Hop = 5,
        MiniTurboReady = 6,
        BoostWhoosh = 7,
        ItemRouletteTick = 8,
        ItemRouletteLock = 9,
        ShellShoot = 10,
        BananaSlip = 11,
        BananaBrakeSaved = 12,
        CrashExplosion = 13,
        LightningStrike = 14,
        BooLaugh = 15,
        LapComplete = 16,
        FinalLapFanfare = 17,
        LakituWarning = 18,
        WallBump = 19,
        Squash = 20
    }

    public sealed class N64AudioSynth : IDisposable
    {
        public static readonly N64AudioSynth Instance = new N64AudioSynth();

        private struct SfxVoice
        {
            public bool Active;
            public float Phase;
            public float FreqStart;
            public float FreqEnd;
            public float Time;
            public float Duration;
            public float Volume;
            public int WaveType; // 0=square/brass, 1=triangle, 2=noise+tone, 3=arpeggio
            public float AuxParam;
        }

        private NativeWaveOut _waveOut;
        private readonly object _lock = new object();

        // Music Sequencer state
        private MusicTrackId _currentTrack = MusicTrackId.None;
        private MusicTrackId _underlyingRaceTrack = MusicTrackId.None;
        private bool _starmanOverride = false;
        private float _tempoMultiplier = 1.0f;
        private double _seqBeatPos = 0.0;
        private double _leadPhase = 0.0;
        private double _harmonyPhase = 0.0;
        private double _bassPhase = 0.0;

        // Player Kart continuous engine state
        private volatile bool _engineActive = false;
        private float _engineSpeedRatio = 0.0f;
        private bool _engineDrifting = false;
        private bool _engineShrunk = false;
        private double _enginePhase = 0.0;
        private double _screechPhase = 0.0;
        private uint _noiseSeed = 0x12345678u;

        // Polyphonic SFX pool
        private const int MaxVoices = 16;
        private readonly SfxVoice[] _voices = new SfxVoice[MaxVoices];
        private int _nextVoice = 0;

        // Melodic pattern tables (MIDI note numbers, 0 = rest)
        private static readonly int[] NotesTitleLead   = { 72, 0, 76, 79, 84, 0, 81, 79, 76, 79, 74, 0, 77, 76, 72, 0 };
        private static readonly int[] NotesTitleBass   = { 48, 48, 55, 55, 57, 57, 53, 53, 48, 52, 50, 50, 43, 47, 48, 55 };

        private static readonly int[] NotesMenuLead    = { 69, 72, 76, 0, 79, 76, 72, 74, 69, 72, 76, 81, 79, 0, 74, 76 };
        private static readonly int[] NotesMenuBass    = { 45, 0, 52, 55, 45, 0, 50, 52, 41, 0, 48, 53, 43, 0, 50, 55 };

        private static readonly int[] NotesRacewayLead = { 72, 76, 79, 84, 83, 79, 76, 79, 81, 77, 72, 77, 79, 76, 74, 79 };
        private static readonly int[] NotesRacewayBass = { 48, 55, 48, 55, 47, 55, 48, 52, 41, 48, 41, 48, 43, 50, 43, 55 };

        private static readonly int[] NotesBeachLead   = { 74, 78, 81, 0, 83, 81, 78, 74, 76, 79, 83, 81, 78, 76, 74, 0 };
        private static readonly int[] NotesBeachBass   = { 50, 57, 54, 57, 47, 54, 50, 57, 52, 59, 55, 59, 45, 52, 50, 57 };

        private static readonly int[] NotesDesertLead  = { 69, 70, 73, 76, 77, 76, 73, 70, 69, 0, 73, 76, 81, 77, 76, 73 };
        private static readonly int[] NotesDesertBass  = { 45, 45, 52, 45, 46, 46, 53, 46, 45, 52, 45, 52, 50, 45, 52, 45 };

        private static readonly int[] NotesSnowLead    = { 79, 84, 83, 79, 81, 84, 79, 76, 77, 81, 79, 76, 74, 77, 79, 0 };
        private static readonly int[] NotesSnowBass    = { 48, 60, 55, 60, 53, 60, 48, 55, 50, 57, 48, 55, 43, 50, 55, 43 };

        private static readonly int[] NotesCastleLead  = { 62, 65, 68, 69, 68, 65, 62, 61, 62, 0, 69, 74, 73, 70, 69, 65 };
        private static readonly int[] NotesCastleBass  = { 38, 38, 45, 38, 44, 38, 43, 37, 38, 45, 38, 45, 37, 43, 45, 38 };

        private static readonly int[] NotesRainbowLead = { 76, 79, 84, 86, 88, 86, 84, 79, 81, 84, 88, 91, 89, 88, 86, 83 };
        private static readonly int[] NotesRainbowBass = { 48, 55, 60, 55, 47, 55, 59, 55, 45, 52, 57, 52, 43, 50, 55, 50 };

        private static readonly int[] NotesStarmanLead = { 79, 79, 79, 76, 79, 0, 79, 76, 77, 77, 77, 74, 77, 0, 77, 74 };
        private static readonly int[] NotesStarmanBass = { 48, 55, 60, 55, 48, 55, 60, 55, 43, 50, 55, 50, 43, 50, 55, 50 };

        private static readonly int[] NotesVictoryLead = { 72, 76, 79, 84, 0, 84, 86, 88, 84, 79, 81, 83, 84, 0, 84, 0 };
        private static readonly int[] NotesVictoryBass = { 48, 52, 55, 60, 53, 57, 60, 53, 48, 55, 43, 50, 48, 55, 48, 0 };

        private static readonly int[] NotesBattleLead  = { 67, 70, 74, 75, 74, 70, 67, 72, 67, 70, 74, 79, 77, 74, 70, 72 };
        private static readonly int[] NotesBattleBass  = { 43, 43, 50, 53, 43, 43, 48, 50, 43, 50, 55, 50, 46, 50, 48, 43 };

        private N64AudioSynth()
        {
        }

        public void Initialize()
        {
            if (_waveOut != null) return;
            _waveOut = new NativeWaveOut(MixSamples);
            _waveOut.Start();
        }

        public void SetMusic(MusicTrackId track, float tempoMultiplier)
        {
            lock (_lock)
            {
                _underlyingRaceTrack = track;
                _tempoMultiplier = MathUtil.Clamp(tempoMultiplier, 0.5f, 1.8f);
                MusicTrackId target = _starmanOverride ? MusicTrackId.StarmanLoop : track;
                if (_currentTrack != target)
                {
                    _currentTrack = target;
                    _seqBeatPos = 0.0;
                }
            }
        }

        public void SetStarmanOverride(bool active)
        {
            lock (_lock)
            {
                if (_starmanOverride == active) return;
                _starmanOverride = active;
                _currentTrack = active ? MusicTrackId.StarmanLoop : _underlyingRaceTrack;
            }
        }

        public void SetTempoMultiplier(float mult)
        {
            _tempoMultiplier = MathUtil.Clamp(mult, 0.5f, 1.8f);
        }

        public void SetEngineState(bool active, float speedRatio, bool drifting, bool shrunk)
        {
            _engineActive = active;
            _engineSpeedRatio = MathUtil.Clamp(speedRatio, 0f, 1.5f);
            _engineDrifting = drifting;
            _engineShrunk = shrunk;
        }

        public void PlaySfx(SfxId id, float volumeScale = 1.0f)
        {
            lock (_lock)
            {
                switch (id)
                {
                    case SfxId.MenuMove:
                        AddVoice(660f, 780f, 0.055f, 0.25f * volumeScale, 1, 0f);
                        break;
                    case SfxId.MenuConfirm:
                        AddVoice(523.25f, 1046.5f, 0.14f, 0.35f * volumeScale, 0, 1f);
                        break;
                    case SfxId.MenuBack:
                        AddVoice(520f, 280f, 0.12f, 0.30f * volumeScale, 1, 0f);
                        break;
                    case SfxId.CountdownTick:
                        AddVoice(440f, 440f, 0.18f, 0.45f * volumeScale, 0, 0f);
                        break;
                    case SfxId.CountdownGo:
                        AddVoice(880f, 880f, 0.42f, 0.55f * volumeScale, 0, 0f);
                        AddVoice(1318.5f, 1318.5f, 0.42f, 0.32f * volumeScale, 1, 0f);
                        break;
                    case SfxId.Hop:
                        AddVoice(210f, 540f, 0.11f, 0.35f * volumeScale, 1, 0f);
                        break;
                    case SfxId.MiniTurboReady:
                        AddVoice(784f, 1175f, 0.12f, 0.32f * volumeScale, 1, 0f);
                        break;
                    case SfxId.BoostWhoosh:
                        AddVoice(180f, 720f, 0.48f, 0.48f * volumeScale, 2, 0.65f);
                        AddVoice(523f, 1046f, 0.32f, 0.28f * volumeScale, 0, 0f);
                        break;
                    case SfxId.ItemRouletteTick:
                        AddVoice(587.3f, 880f, 0.045f, 0.20f * volumeScale, 1, 0f);
                        break;
                    case SfxId.ItemRouletteLock:
                        AddVoice(659.3f, 1318.5f, 0.22f, 0.40f * volumeScale, 3, 14f);
                        break;
                    case SfxId.ShellShoot:
                        AddVoice(620f, 240f, 0.16f, 0.40f * volumeScale, 0, 0f);
                        break;
                    case SfxId.BananaSlip:
                        AddVoice(750f, 190f, 0.42f, 0.42f * volumeScale, 3, 18f);
                        break;
                    case SfxId.BananaBrakeSaved:
                        AddVoice(659.25f, 987.77f, 0.24f, 0.42f * volumeScale, 1, 0f);
                        break;
                    case SfxId.CrashExplosion:
                        AddVoice(160f, 45f, 0.52f, 0.58f * volumeScale, 2, 0.85f);
                        break;
                    case SfxId.LightningStrike:
                        AddVoice(980f, 90f, 0.72f, 0.65f * volumeScale, 2, 0.75f);
                        AddVoice(1480f, 220f, 0.45f, 0.42f * volumeScale, 0, 0f);
                        break;
                    case SfxId.BooLaugh:
                        AddVoice(520f, 760f, 0.45f, 0.38f * volumeScale, 3, 22f);
                        break;
                    case SfxId.LapComplete:
                        AddVoice(523.25f, 1046.5f, 0.36f, 0.42f * volumeScale, 3, 10f);
                        break;
                    case SfxId.FinalLapFanfare:
                        AddVoice(659.25f, 1318.5f, 0.62f, 0.52f * volumeScale, 3, 12f);
                        break;
                    case SfxId.LakituWarning:
                        AddVoice(880f, 622f, 0.22f, 0.36f * volumeScale, 0, 0f);
                        break;
                    case SfxId.WallBump:
                        AddVoice(140f, 65f, 0.14f, 0.42f * volumeScale, 2, 0.6f);
                        break;
                    case SfxId.Squash:
                        AddVoice(380f, 95f, 0.28f, 0.48f * volumeScale, 0, 0f);
                        break;
                }
            }
        }

        private void AddVoice(float fStart, float fEnd, float dur, float vol, int waveType, float aux)
        {
            SfxVoice v = new SfxVoice();
            v.Active = true;
            v.Phase = 0f;
            v.FreqStart = fStart;
            v.FreqEnd = fEnd;
            v.Time = 0f;
            v.Duration = dur;
            v.Volume = vol;
            v.WaveType = waveType;
            v.AuxParam = aux;

            _voices[_nextVoice] = v;
            _nextVoice = (_nextVoice + 1) % MaxVoices;
        }

        private float NextNoise()
        {
            _noiseSeed ^= _noiseSeed << 13;
            _noiseSeed ^= _noiseSeed >> 17;
            _noiseSeed ^= _noiseSeed << 5;
            return ((_noiseSeed & 0xFFFFu) / 32768.0f) - 1.0f;
        }

        private static double MidiToFreq(int midi)
        {
            if (midi <= 0) return 0.0;
            return 440.0 * Math.Pow(2.0, (midi - 69) / 12.0);
        }

        public void MixSamples(short[] buffer, int frames)
        {
            float musicVol = GameConfig.Instance.MusicVolume * 0.26f;
            float sfxVol = GameConfig.Instance.SfxVolume * 0.45f;
            double dt = 1.0 / NativeWaveOut.SampleRate;

            lock (_lock)
            {
                int[] leadSeq = null;
                int[] bassSeq = null;
                double baseBpm = 132.0;

                switch (_currentTrack)
                {
                    case MusicTrackId.TitleGroove:      leadSeq = NotesTitleLead;   bassSeq = NotesTitleBass;   baseBpm = 134.0; break;
                    case MusicTrackId.MenuSetup:        leadSeq = NotesMenuLead;    bassSeq = NotesMenuBass;    baseBpm = 122.0; break;
                    case MusicTrackId.RacewayCircuit:   leadSeq = NotesRacewayLead; bassSeq = NotesRacewayBass; baseBpm = 144.0; break;
                    case MusicTrackId.FarmAndBeach:     leadSeq = NotesBeachLead;   bassSeq = NotesBeachBass;   baseBpm = 136.0; break;
                    case MusicTrackId.DesertAndHighway: leadSeq = NotesDesertLead;  bassSeq = NotesDesertBass;  baseBpm = 142.0; break;
                    case MusicTrackId.SnowAndIce:       leadSeq = NotesSnowLead;    bassSeq = NotesSnowBass;    baseBpm = 138.0; break;
                    case MusicTrackId.CastleAndSpooky:  leadSeq = NotesCastleLead;  bassSeq = NotesCastleBass;  baseBpm = 134.0; break;
                    case MusicTrackId.RainbowRoad:      leadSeq = NotesRainbowLead; bassSeq = NotesRainbowBass; baseBpm = 148.0; break;
                    case MusicTrackId.StarmanLoop:      leadSeq = NotesStarmanLead; bassSeq = NotesStarmanBass; baseBpm = 172.0; break;
                    case MusicTrackId.VictoryPodium:    leadSeq = NotesVictoryLead; bassSeq = NotesVictoryBass; baseBpm = 132.0; break;
                    case MusicTrackId.BattleArena:      leadSeq = NotesBattleLead;  bassSeq = NotesBattleBass;  baseBpm = 140.0; break;
                }

                double stepsPerSec = (baseBpm * _tempoMultiplier / 60.0) * 2.0; // Eighth-note grid

                for (int i = 0; i < frames; i++)
                {
                    float left = 0f;
                    float right = 0f;

                    // 1. N64 Multi-Channel Music Synth
                    if (leadSeq != null && musicVol > 0.001f)
                    {
                        _seqBeatPos += stepsPerSec * dt;
                        int step = ((int)_seqBeatPos) % leadSeq.Length;
                        double stepFrac = _seqBeatPos - Math.Floor(_seqBeatPos);

                        int leadNote = leadSeq[step];
                        int bassNote = bassSeq[step];
                        float envLead = (float)Math.Max(0.0, 1.0 - stepFrac * 0.72);
                        float envBass = (float)Math.Max(0.0, 1.0 - stepFrac * 0.90);

                        if (leadNote > 0)
                        {
                            double freq = MidiToFreq(leadNote);
                            _leadPhase += freq * dt;
                            if (_leadPhase >= 1.0) _leadPhase -= 1.0;
                            // Warm N64 pulse-saw lead + major/minor fifth shimmer
                            float pulse = (_leadPhase < 0.35) ? 0.65f : -0.35f;
                            float sine = (float)Math.Sin(_leadPhase * MathUtil.TWO_PI);
                            float sample = (0.55f * pulse + 0.45f * sine) * envLead * musicVol;

                            _harmonyPhase += (freq * 0.74915) * dt;
                            if (_harmonyPhase >= 1.0) _harmonyPhase -= 1.0;
                            float harm = (float)Math.Sin(_harmonyPhase * MathUtil.TWO_PI) * 0.25f * envLead * musicVol;

                            left += sample + harm * 0.6f;
                            right += sample * 0.85f + harm;
                        }

                        if (bassNote > 0)
                        {
                            double bfreq = MidiToFreq(bassNote);
                            _bassPhase += bfreq * dt;
                            if (_bassPhase >= 1.0) _bassPhase -= 1.0;
                            float tri = (float)(1.0 - 4.0 * Math.Abs(Math.Round(_bassPhase - 0.25) - (_bassPhase - 0.25)));
                            float bSample = tri * envBass * musicVol * 0.85f;
                            left += bSample;
                            right += bSample;
                        }

                        // Crisp hi-hat / snare groove on off-beats
                        if (stepFrac < 0.14)
                        {
                            float n = NextNoise();
                            float perc = ((step % 4 == 2) ? 0.22f : 0.08f) * (float)(1.0 - stepFrac / 0.14) * musicVol;
                            left += n * perc;
                            right += n * perc;
                        }
                    }

                    // 2. Continuous Player Kart Engine & Tire Drift Screech
                    if (_engineActive && sfxVol > 0.001f)
                    {
                        float pitchScale = _engineShrunk ? 1.65f : 1.0f;
                        double engFreq = (52.0 + _engineSpeedRatio * 128.0) * pitchScale;
                        _enginePhase += engFreq * dt;
                        if (_enginePhase >= 1.0) _enginePhase -= 1.0;

                        // Two-stroke N64 kart buzz (fundamental + 2nd + 3rd harmonic)
                        float e1 = (_enginePhase < 0.42) ? 0.5f : -0.5f;
                        float e2 = (float)Math.Sin(_enginePhase * MathUtil.TWO_PI * 2.0) * 0.35f;
                        float engGain = (0.09f + _engineSpeedRatio * 0.11f) * sfxVol;
                        float engOut = (e1 + e2) * engGain;
                        left += engOut;
                        right += engOut;

                        if (_engineDrifting)
                        {
                            _screechPhase += 920.0 * dt;
                            if (_screechPhase >= 1.0) _screechPhase -= 1.0;
                            float screech = ((float)Math.Sin(_screechPhase * MathUtil.TWO_PI) * 0.6f + NextNoise() * 0.4f) * 0.09f * sfxVol;
                            left += screech;
                            right += screech;
                        }
                    }

                    // 3. Polyphonic Sound Effects
                    for (int v = 0; v < MaxVoices; v++)
                    {
                        if (!_voices[v].Active) continue;
                        SfxVoice sv = _voices[v];
                        sv.Time += (float)dt;
                        if (sv.Time >= sv.Duration)
                        {
                            sv.Active = false;
                            _voices[v] = sv;
                            continue;
                        }

                        float tNorm = sv.Time / sv.Duration;
                        float env = 1.0f - tNorm;
                        float curFreq = sv.FreqStart + (sv.FreqEnd - sv.FreqStart) * tNorm;
                        if (sv.WaveType == 3 && sv.AuxParam > 0f)
                        {
                            // Arpeggio / vibrato modulation
                            int arpStep = (int)(sv.Time * sv.AuxParam);
                            if ((arpStep & 1) == 1) curFreq *= 1.2599f;
                        }

                        sv.Phase += curFreq * (float)dt;
                        if (sv.Phase >= 1.0f) sv.Phase -= (float)Math.Floor(sv.Phase);

                        float wave = 0f;
                        if (sv.WaveType == 0 || sv.WaveType == 3)
                        {
                            wave = (sv.Phase < 0.5f) ? 0.7f : -0.7f;
                        }
                        else if (sv.WaveType == 1)
                        {
                            wave = (float)Math.Sin(sv.Phase * MathUtil.TWO_PI);
                        }
                        else
                        {
                            wave = NextNoise() * sv.AuxParam + (float)Math.Sin(sv.Phase * MathUtil.TWO_PI) * (1.0f - sv.AuxParam);
                        }

                        float sOut = wave * env * sv.Volume * sfxVol;
                        left += sOut;
                        right += sOut;
                        _voices[v] = sv;
                    }

                    // Soft clip to 16-bit signed range
                    int outL = (int)(MathUtil.Clamp(left, -0.98f, 0.98f) * 32000f);
                    int outR = (int)(MathUtil.Clamp(right, -0.98f, 0.98f) * 32000f);
                    buffer[i * 2] = (short)outL;
                    buffer[i * 2 + 1] = (short)outR;
                }
            }
        }

        public void Dispose()
        {
            if (_waveOut != null)
            {
                _waveOut.Dispose();
                _waveOut = null;
            }
        }
    }
}
