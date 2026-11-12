"""Opt-in policies for the evidence branch; not validated production defaults."""
import numpy as np


def guarded_level(audio, sr):
    """Lift quiet, dynamic material only; never amplify silence or steady noise.

    RMS guard and frame dynamics are conservative heuristics, NOT a reliable SNR or
    reverb classifier. Changes are bounded to +24 dB with .95 peak headroom.
    """
    y = np.asarray(audio, dtype=np.float32)
    rms = float(np.sqrt(np.mean(y.astype(float)**2))) if y.size else 0.0
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    info = {'rms': rms, 'peak': peak, 'gain_db': 0.0, 'reason': 'level outside quiet range'}
    if not np.isfinite(y).all():
        raise ValueError('Non-finite audio samples')
    if not .0005 <= rms < .012 or peak == 0:
        return y, info
    hop = max(1, int(sr*.05))
    frames = [float(np.sqrt(np.mean(y[i:i+hop].astype(float)**2))) for i in range(0,len(y),hop)]
    dynamic = float(np.percentile(frames,90)/max(np.percentile(frames,10),1e-8))
    info['frame_dynamic_ratio'] = dynamic
    if dynamic < 3 or peak/max(rms,1e-8) < 1.5:
        info['reason'] = 'insufficient dynamic evidence; do not amplify possible noise'
        return y, info
    gain = min(.05/rms, 10**(24/20), .95/peak)
    info.update(gain_db=float(20*np.log10(gain)), reason='guarded quiet-input lift')
    return (y*gain).astype(np.float32), info
