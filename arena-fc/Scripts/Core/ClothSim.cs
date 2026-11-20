// Arena FC — simple cloth/hair simulation for kit and hair jiggle.
// Verlet integration with distance constraints. Runs on CPU, <0.1ms per player.
//
// IMPORTANT: Scripts/Core must stay engine-free.  This file used to import
// Godot for Vector3, which broke every consumer that compiles Core without the
// Godot assemblies (Server/ArenaFC.Server.csproj, Tests/*.csproj).  Core maths
// is System.Numerics — the Godot layer converts at the boundary (see
// MatchView.G / CharacterEditor).  CI enforces this with a static check.
using System;
using System.Collections.Generic;
using System.Numerics;

namespace ArenaFC.Core;

/// <summary>
/// Simple cloth particle system for kit/hair jiggle.
/// Each particle has position, previous position, and pinned flag.
/// Constraints maintain shape; gravity and wind apply forces.
/// </summary>
public class ClothParticle
{
    public Vector3 Position;
    public Vector3 Previous;
    public bool Pinned;
    public float Mass = 1f;
}

public class ClothConstraint
{
    public int A, B;
    public float RestLength;
}

/// <summary>
/// Lightweight cloth simulation for player kits and hair.
/// Designed for 18-bone skeleton — particles attached to bone positions.
/// </summary>
public class ClothSim
{
    private readonly List<ClothParticle> _particles = new();
    private readonly List<ClothConstraint> _constraints = new();
    private const float Gravity = -9.81f;
    private const int Iterations = 3;

    public Vector3 Wind = new(0.5f, 0, 0.2f);
    public float Damping = 0.98f;

    public void AddParticle(Vector3 pos, bool pinned = false)
    {
        _particles.Add(new ClothParticle
        {
            Position = pos,
            Previous = pos,
            Pinned = pinned,
        });
    }

    public void AddConstraint(int a, int b, float restLength)
    {
        if (a < 0 || b < 0 || a >= _particles.Count || b >= _particles.Count || a == b) return;
        _constraints.Add(new ClothConstraint { A = a, B = b, RestLength = restLength });
    }

    public void Step(float dt, Vector3[] bonePositions)
    {
        if (dt <= 0f) return;
        dt = MathF.Min(dt, 1f / 20f);            // clamp hitches, keep it stable
        Vector3 accel = Vector3.UnitY * Gravity + Wind;
        float dt2 = dt * dt;

        // Update unpinned particles
        foreach (var p in _particles)
        {
            if (p.Pinned || p.Mass <= 0f) continue;
            var vel = (p.Position - p.Previous) * Damping;
            p.Previous = p.Position;
            p.Position += vel + accel * dt2;
        }

        // Satisfy constraints
        for (int iter = 0; iter < Iterations; iter++)
        {
            foreach (var c in _constraints)
            {
                var a = _particles[c.A];
                var b = _particles[c.B];
                var delta = b.Position - a.Position;
                var dist = delta.Length();
                if (dist < 1e-6f) continue;
                var diff = (dist - c.RestLength) / dist;
                if (!a.Pinned) a.Position += delta * 0.5f * diff;
                if (!b.Pinned) b.Position -= delta * 0.5f * diff;
            }
        }

        // Pin to bone positions
        if (bonePositions != null)
            for (int i = 0; i < _particles.Count && i < bonePositions.Length; i++)
            {
                if (_particles[i].Pinned)
                {
                    _particles[i].Position = bonePositions[i];
                    _particles[i].Previous = bonePositions[i];
                }
            }
    }

    public int ParticleCount => _particles.Count;
    public Vector3 GetPosition(int index) => _particles[index].Position;
}
