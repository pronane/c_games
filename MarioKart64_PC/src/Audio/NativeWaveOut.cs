using System;
using System.Runtime.InteropServices;
using System.Threading;
using MarioKart64.Input;

namespace MarioKart64.Audio
{
    [StructLayout(LayoutKind.Sequential, Pack = 1)]
    public struct WAVEFORMATEX
    {
        public ushort wFormatTag;
        public ushort nChannels;
        public uint nSamplesPerSec;
        public uint nAvgBytesPerSec;
        public ushort nBlockAlign;
        public ushort wBitsPerSample;
        public ushort cbSize;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct WAVEHDR
    {
        public IntPtr lpData;
        public uint dwBufferLength;
        public uint dwBytesRecorded;
        public IntPtr dwUser;
        public uint dwFlags;
        public uint dwLoops;
        public IntPtr lpNext;
        public IntPtr reserved;
    }

    public sealed class NativeWaveOut : IDisposable
    {
        private const uint WAVE_MAPPER = 0xFFFFFFFF;
        private const ushort WAVE_FORMAT_PCM = 1;
        private const uint WHDR_DONE = 0x00000001;
        private const uint WHDR_PREPARED = 0x00000002;

        public const int SampleRate = 44100;
        public const int Channels = 2;
        public const int FramesPerBuffer = 1024; // ~23.2 ms per buffer
        public const int BufferCount = 4;

        [DllImport("winmm.dll")]
        private static extern int waveOutOpen(out IntPtr hWaveOut, uint uDeviceID, ref WAVEFORMATEX lpFormat, IntPtr dwCallback, IntPtr dwInstance, uint dwFlags);

        [DllImport("winmm.dll")]
        private static extern int waveOutPrepareHeader(IntPtr hWaveOut, IntPtr lpWaveOutHdr, uint uSize);

        [DllImport("winmm.dll")]
        private static extern int waveOutUnprepareHeader(IntPtr hWaveOut, IntPtr lpWaveOutHdr, uint uSize);

        [DllImport("winmm.dll")]
        private static extern int waveOutWrite(IntPtr hWaveOut, IntPtr lpWaveOutHdr, uint uSize);

        [DllImport("winmm.dll")]
        private static extern int waveOutReset(IntPtr hWaveOut);

        [DllImport("winmm.dll")]
        private static extern int waveOutClose(IntPtr hWaveOut);

        private IntPtr _hWaveOut = IntPtr.Zero;
        private readonly short[][] _sampleBuffers = new short[BufferCount][];
        private GCHandle[] _bufferPins = new GCHandle[BufferCount];
        private IntPtr[] _hdrPtrs = new IntPtr[BufferCount];
        private Thread _audioThread;
        private volatile bool _running;
        private readonly Action<short[], int> _fillCallback;

        public NativeWaveOut(Action<short[], int> fillCallback)
        {
            _fillCallback = fillCallback;
        }

        public bool Start()
        {
            if (!NativeInput.IsWindowsPlatform()) return false;

            try
            {
                WAVEFORMATEX fmt = new WAVEFORMATEX();
                fmt.wFormatTag = WAVE_FORMAT_PCM;
                fmt.nChannels = Channels;
                fmt.nSamplesPerSec = SampleRate;
                fmt.wBitsPerSample = 16;
                fmt.nBlockAlign = (ushort)(Channels * (fmt.wBitsPerSample / 8));
                fmt.nAvgBytesPerSec = fmt.nSamplesPerSec * fmt.nBlockAlign;
                fmt.cbSize = 0;

                int res = waveOutOpen(out _hWaveOut, WAVE_MAPPER, ref fmt, IntPtr.Zero, IntPtr.Zero, 0);
                if (res != 0 || _hWaveOut == IntPtr.Zero)
                {
                    _hWaveOut = IntPtr.Zero;
                    return false;
                }

                uint hdrSize = (uint)Marshal.SizeOf(typeof(WAVEHDR));
                for (int i = 0; i < BufferCount; i++)
                {
                    _sampleBuffers[i] = new short[FramesPerBuffer * Channels];
                    _bufferPins[i] = GCHandle.Alloc(_sampleBuffers[i], GCHandleType.Pinned);

                    WAVEHDR hdr = new WAVEHDR();
                    hdr.lpData = _bufferPins[i].AddrOfPinnedObject();
                    hdr.dwBufferLength = (uint)(_sampleBuffers[i].Length * sizeof(short));
                    hdr.dwFlags = 0;
                    hdr.dwLoops = 0;

                    _hdrPtrs[i] = Marshal.AllocHGlobal((int)hdrSize);
                    Marshal.StructureToPtr(hdr, _hdrPtrs[i], false);
                    waveOutPrepareHeader(_hWaveOut, _hdrPtrs[i], hdrSize);

                    // Prime buffer with initial audio
                    _fillCallback(_sampleBuffers[i], FramesPerBuffer);
                    waveOutWrite(_hWaveOut, _hdrPtrs[i], hdrSize);
                }

                _running = true;
                _audioThread = new Thread(AudioLoop);
                _audioThread.IsBackground = true;
                _audioThread.Priority = ThreadPriority.AboveNormal;
                _audioThread.Name = "MK64_WaveOutMixer";
                _audioThread.Start();
                return true;
            }
            catch
            {
                Dispose();
                return false;
            }
        }

        private void AudioLoop()
        {
            uint hdrSize = (uint)Marshal.SizeOf(typeof(WAVEHDR));
            while (_running)
            {
                bool refilledAny = false;
                for (int i = 0; i < BufferCount; i++)
                {
                    if (!_running) break;
                    WAVEHDR hdr = (WAVEHDR)Marshal.PtrToStructure(_hdrPtrs[i], typeof(WAVEHDR));
                    if ((hdr.dwFlags & WHDR_DONE) != 0)
                    {
                        _fillCallback(_sampleBuffers[i], FramesPerBuffer);
                        waveOutWrite(_hWaveOut, _hdrPtrs[i], hdrSize);
                        refilledAny = true;
                    }
                }
                if (!refilledAny)
                {
                    Thread.Sleep(4);
                }
            }
        }

        public void Dispose()
        {
            _running = false;
            if (_audioThread != null)
            {
                try { _audioThread.Join(300); } catch { }
                _audioThread = null;
            }

            if (_hWaveOut != IntPtr.Zero)
            {
                try { waveOutReset(_hWaveOut); } catch { }
                uint hdrSize = (uint)Marshal.SizeOf(typeof(WAVEHDR));
                for (int i = 0; i < BufferCount; i++)
                {
                    if (_hdrPtrs[i] != IntPtr.Zero)
                    {
                        try { waveOutUnprepareHeader(_hWaveOut, _hdrPtrs[i], hdrSize); } catch { }
                        Marshal.FreeHGlobal(_hdrPtrs[i]);
                        _hdrPtrs[i] = IntPtr.Zero;
                    }
                    if (_bufferPins[i].IsAllocated)
                    {
                        _bufferPins[i].Free();
                    }
                }
                try { waveOutClose(_hWaveOut); } catch { }
                _hWaveOut = IntPtr.Zero;
            }
        }
    }
}
