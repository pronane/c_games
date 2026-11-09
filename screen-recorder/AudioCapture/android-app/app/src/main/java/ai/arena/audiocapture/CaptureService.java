package ai.arena.audiocapture;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.ContentValues;
import android.content.Intent;
import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Environment;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.ParcelFileDescriptor;
import android.os.Process;
import android.provider.MediaStore;
import android.system.Os;
import android.util.Log;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.RandomAccessFile;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;

public class CaptureService extends Service {
    public static final String ACTION_START = "ai.arena.audiocapture.START";
    public static final String ACTION_STOP = "ai.arena.audiocapture.STOP";
    public static final String EXTRA_RESULT_CODE = "resultCode";
    public static final String EXTRA_RESULT_DATA = "resultData";
    private static final String CHANNEL = "audio_capture";
    private static final int NOTIFICATION_ID = 4172;
    private static final int RATE = 48000, CHANNELS = 2;
    private final AtomicBoolean active = new AtomicBoolean(false);
    private AudioRecord audioRecord;
    private MediaProjection projection;
    private Thread worker;
    private File tempFile;

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) { stopSelf(); return START_NOT_STICKY; }
        if (ACTION_STOP.equals(intent.getAction())) { stopCapture(null); return START_NOT_STICKY; }
        if (ACTION_START.equals(intent.getAction())) beginCapture(intent);
        return START_NOT_STICKY;
    }

    private void beginCapture(Intent intent) {
        if (active.get()) return;
        createChannel();
        if (Build.VERSION.SDK_INT >= 29)
            startForeground(NOTIFICATION_ID, notification(), android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION);
        else startForeground(NOTIFICATION_ID, notification());
        try {
            int resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, 0);
            Intent resultData = intent.getParcelableExtra(EXTRA_RESULT_DATA);
            MediaProjectionManager manager = (MediaProjectionManager)getSystemService(MEDIA_PROJECTION_SERVICE);
            projection = manager.getMediaProjection(resultCode, resultData);
            if (projection == null) throw new IllegalStateException("Android did not provide a playback capture session.");
            MediaProjection.Callback callback = new MediaProjection.Callback() {
                @Override public void onStop() { stopCapture("Android ended playback capture."); }
            };
            projection.registerCallback(callback, new Handler(Looper.getMainLooper()));
            android.media.AudioPlaybackCaptureConfiguration config =
                    new android.media.AudioPlaybackCaptureConfiguration.Builder(projection)
                            .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
                            .addMatchingUsage(AudioAttributes.USAGE_GAME)
                            .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN)
                            .build();
            AudioFormat format = new AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(RATE).setChannelMask(AudioFormat.CHANNEL_IN_STEREO).build();
            audioRecord = new AudioRecord.Builder().setAudioFormat(format)
                    .setBufferSizeInBytes(Math.max(AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_STEREO,
                            AudioFormat.ENCODING_PCM_16BIT) * 2, 16384))
                    .setAudioPlaybackCaptureConfig(config).build();
            if (audioRecord.getState() != AudioRecord.STATE_INITIALIZED) throw new IllegalStateException("Audio capture could not be initialized on this device.");
            tempFile = new File(getCacheDir(), "capture-" + System.currentTimeMillis() + ".wavpart");
            audioRecord.startRecording();
            active.set(true);
            worker = new Thread(this::recordLoop, "playback-audio-capture");
            worker.start();
            updateNotification("Recording app playback audio");
        } catch (Exception e) {
            Log.e("AudioCapture", "Could not start playback capture", e);
            stopCapture("Could not start: " + e.getMessage());
        }
    }

    private void recordLoop() {
        Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO);
        short[] samples = new short[8192];
        try (FileOutputStream out = new FileOutputStream(tempFile)) {
            out.write(new byte[44]);
            while (active.get()) {
                int n = audioRecord.read(samples, 0, samples.length, AudioRecord.READ_BLOCKING);
                if (n > 0) {
                    ByteBuffer bytes = ByteBuffer.allocate(n * 2).order(ByteOrder.LITTLE_ENDIAN);
                    for (int i = 0; i < n; i++) bytes.putShort(samples[i]);
                    out.write(bytes.array());
                } else if (n < 0) {
                    Log.w("AudioCapture", "AudioRecord read returned " + n);
                    break;
                }
            }
            out.flush();
        } catch (Exception e) { Log.e("AudioCapture", "Capture writer failed", e); }
    }

    private synchronized void stopCapture(String message) {
        boolean wasActive = active.getAndSet(false);
        if (audioRecord != null) try { audioRecord.stop(); } catch (Exception ignored) { }
        if (worker != null && worker != Thread.currentThread()) {
            try { worker.join(2500); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
        }
        if (audioRecord != null) { try { audioRecord.release(); } catch (Exception ignored) { } audioRecord = null; }
        String saved = null;
        if (wasActive && tempFile != null && tempFile.exists()) {
            try { saved = publishWav(tempFile); }
            catch (Exception e) { Log.e("AudioCapture", "Could not save capture", e); message = "Could not save recording: " + e.getMessage(); }
        }
        if (projection != null) { MediaProjection oldProjection = projection; projection = null; try { oldProjection.stop(); } catch (Exception ignored) { } }
        if (tempFile != null) { // The app-private intermediate is removed after publishing.
            //noinspection ResultOfMethodCallIgnored
            tempFile.delete(); tempFile = null;
        }
        stopForeground(true);
        if (saved != null) broadcast("Saved recording: " + saved);
        else if (message != null) broadcast(message);
        else if (wasActive) broadcast("Capture stopped. No audio was recorded.");
        stopSelf();
    }

    private String publishWav(File file) throws Exception {
        try (RandomAccessFile wav = new RandomAccessFile(file, "rw")) {
            long length = wav.length();
            long dataBytes = length - 44;
            if (dataBytes <= 0) throw new IllegalStateException("No audio samples were captured.");
            wav.seek(0); wav.write(new byte[]{'R','I','F','F'}); writeLe32(wav, (int)(length - 8));
            wav.write(new byte[]{'W','A','V','E','f','m','t',' '}); writeLe32(wav, 16);
            writeLe16(wav, 1); writeLe16(wav, CHANNELS); writeLe32(wav, RATE);
            writeLe32(wav, RATE * CHANNELS * 2); writeLe16(wav, CHANNELS * 2); writeLe16(wav, 16);
            wav.write(new byte[]{'d','a','t','a'}); writeLe32(wav, (int)dataBytes);
        }
        String stamp = new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(new Date());
        String name = "AudioCapture-" + stamp + ".wav";
        ContentValues values = new ContentValues();
        values.put(MediaStore.Audio.Media.DISPLAY_NAME, name);
        values.put(MediaStore.Audio.Media.MIME_TYPE, "audio/wav");
        values.put(MediaStore.Audio.Media.RELATIVE_PATH, Environment.DIRECTORY_MUSIC + "/Audio Capture");
        if (Build.VERSION.SDK_INT >= 29) values.put(MediaStore.Audio.Media.IS_PENDING, 1);
        android.net.Uri uri = getContentResolver().insert(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, values);
        if (uri == null) throw new IllegalStateException("Could not create a media-library entry.");
        try (FileInputStream in = new FileInputStream(file); OutputStream out = getContentResolver().openOutputStream(uri, "w")) {
            if (out == null) throw new IllegalStateException("Could not open the output recording.");
            byte[] buffer = new byte[65536]; int n;
            while ((n = in.read(buffer)) != -1) out.write(buffer, 0, n);
            out.flush();
        }
        if (Build.VERSION.SDK_INT >= 29) {
            ContentValues done = new ContentValues(); done.put(MediaStore.Audio.Media.IS_PENDING, 0);
            getContentResolver().update(uri, done, null, null);
        }
        return name;
    }

    private static void writeLe16(RandomAccessFile f, int x) throws Exception { f.write(x & 255); f.write((x >>> 8) & 255); }
    private static void writeLe32(RandomAccessFile f, int x) throws Exception { f.write(x & 255); f.write((x >>> 8) & 255); f.write((x >>> 16) & 255); f.write((x >>> 24) & 255); }

    private void broadcast(String message) {
        Intent i = new Intent("ai.arena.audiocapture.SAVED").setPackage(getPackageName()).putExtra("message", message);
        sendBroadcast(i);
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(CHANNEL, "Audio capture", NotificationManager.IMPORTANCE_LOW);
            ((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(channel);
        }
    }
    private Notification notification() { return buildNotification("Starting playback capture…"); }
    private void updateNotification(String text) {
        ((NotificationManager)getSystemService(NOTIFICATION_SERVICE)).notify(NOTIFICATION_ID, buildNotification(text));
    }
    private Notification buildNotification(String text) {
        Intent stop = new Intent(this, CaptureService.class).setAction(ACTION_STOP);
        PendingIntent action = PendingIntent.getService(this, 1, stop, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, CHANNEL) : new Notification.Builder(this);
        b.setSmallIcon(android.R.drawable.ic_btn_speak_now).setContentTitle("Audio Capture Studio")
                .setContentText(text).setOngoing(true).addAction(android.R.drawable.ic_media_pause, "Stop", action);
        return b.build();
    }

    @Override public IBinder onBind(Intent intent) { return null; }
    @Override public void onDestroy() {
        if (active.get()) stopCapture(null);
        super.onDestroy();
    }
}
