package ai.arena.audiocapture;

import android.Manifest;
import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.ContentUris;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.graphics.Color;
import android.graphics.Typeface;

import java.util.ArrayList;
import java.util.List;

public class MainActivity extends Activity {
    private static final int REQ_AUDIO = 10;
    private static final int REQ_CAPTURE = 11;
    private static final String ACTION_SAVED = "ai.arena.audiocapture.SAVED";
    private LinearLayout root, recordings;
    private TextView status;
    private Button startButton, stopButton;
    private MediaPlayer mediaPlayer;
    private BroadcastReceiver savedReceiver;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        buildUi();
        IntentFilter filter = new IntentFilter(ACTION_SAVED);
        savedReceiver = new BroadcastReceiver() {
            @Override public void onReceive(Context c, Intent i) {
                status.setText(i.getStringExtra("message"));
                setRecording(false);
                loadRecordings();
            }
        };
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(savedReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        else registerReceiver(savedReceiver, filter);
        loadRecordings();
    }

    private void buildUi() {
        root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(22), dp(24), dp(22), dp(20)); root.setBackgroundColor(Color.rgb(18, 21, 28));
        ScrollView scroll = new ScrollView(this); scroll.addView(root);
        setContentView(scroll);
        TextView title = new TextView(this); title.setText("Audio Capture Studio"); title.setTextSize(25);
        title.setTypeface(null, Typeface.BOLD); title.setTextColor(Color.WHITE); root.addView(title);
        TextView intro = new TextView(this);
        intro.setText("Record audio playing in other apps — not microphone audio. Android will ask you to approve capture each time.");
        intro.setTextSize(14); intro.setTextColor(Color.LTGRAY); intro.setPadding(0, dp(8), 0, dp(12)); root.addView(intro);
        TextView caveat = new TextView(this);
        caveat.setText("Some apps block playback capture, and protected audio may be silent. Only audio that Android permits can be recorded.");
        caveat.setTextSize(12); caveat.setTextColor(Color.rgb(255, 190, 90)); caveat.setPadding(0, 0, 0, dp(18)); root.addView(caveat);
        LinearLayout buttons = new LinearLayout(this); buttons.setOrientation(LinearLayout.HORIZONTAL);
        startButton = button("Start capture", 0xff2563eb); stopButton = button("Stop and save", 0xffb91c1c);
        buttons.addView(startButton, new LinearLayout.LayoutParams(0, dp(52), 1));
        LinearLayout.LayoutParams stopLp = new LinearLayout.LayoutParams(0, dp(52), 1); stopLp.leftMargin = dp(10);
        buttons.addView(stopButton, stopLp); root.addView(buttons);
        status = new TextView(this); status.setText("Ready. Your recordings are saved on this device.");
        status.setTextColor(Color.rgb(134, 239, 172)); status.setTextSize(13); status.setPadding(0, dp(14), 0, dp(20)); root.addView(status);
        TextView header = new TextView(this); header.setText("Your recordings"); header.setTextColor(Color.WHITE);
        header.setTextSize(18); header.setTypeface(null, Typeface.BOLD); root.addView(header);
        recordings = new LinearLayout(this); recordings.setOrientation(LinearLayout.VERTICAL);
        root.addView(recordings, new LinearLayout.LayoutParams(-1, -2));
        startButton.setOnClickListener(v -> requestCapture());
        stopButton.setOnClickListener(v -> {
            status.setText("Finishing and saving WAV…");
            startService(new Intent(this, CaptureService.class).setAction(CaptureService.ACTION_STOP));
            stopButton.setEnabled(false);
        });
        setRecording(false);
    }

    private Button button(String text, int color) {
        Button b = new Button(this); b.setText(text); b.setTextColor(Color.WHITE); b.setAllCaps(false);
        b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(color)); return b;
    }

    private void requestCapture() {
        if (Build.VERSION.SDK_INT >= 23 && checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_AUDIO);
            return;
        }
        Intent capture = ((android.media.projection.MediaProjectionManager)getSystemService(MEDIA_PROJECTION_SERVICE)).createScreenCaptureIntent();
        startActivityForResult(capture, REQ_CAPTURE);
    }

    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results);
        if (request == REQ_AUDIO && results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) requestCapture();
        else if (request == REQ_AUDIO) status.setText("Microphone permission is required by Android for playback capture. No microphone input is recorded.");
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == REQ_CAPTURE) {
            if (result != RESULT_OK || data == null) { status.setText("Capture permission was not granted."); return; }
            Intent service = new Intent(this, CaptureService.class)
                    .setAction(CaptureService.ACTION_START)
                    .putExtra(CaptureService.EXTRA_RESULT_CODE, result)
                    .putExtra(CaptureService.EXTRA_RESULT_DATA, data);
            if (Build.VERSION.SDK_INT >= 26) startForegroundService(service); else startService(service);
            status.setText("Recording app playback audio…"); setRecording(true);
        }
    }

    private void setRecording(boolean recording) {
        if (startButton != null) startButton.setEnabled(!recording);
        if (stopButton != null) { stopButton.setEnabled(recording); stopButton.setText(recording ? "Stop and save" : "Not recording"); }
    }

    private void loadRecordings() {
        recordings.removeAllViews();
        List<Row> rows = new ArrayList<>();
        Uri collection = MediaStore.Audio.Media.EXTERNAL_CONTENT_URI;
        String[] projection = {MediaStore.Audio.Media._ID, MediaStore.Audio.Media.DISPLAY_NAME, MediaStore.Audio.Media.DATE_ADDED};
        String selection = MediaStore.Audio.Media.RELATIVE_PATH + "=?";
        String[] args = {Environment.DIRECTORY_MUSIC + "/Audio Capture/"};
        try (Cursor c = getContentResolver().query(collection, projection, selection, args, MediaStore.Audio.Media.DATE_ADDED + " DESC")) {
            if (c != null) while (c.moveToNext()) {
                long id = c.getLong(0); String name = c.getString(1);
                rows.add(new Row(ContentUris.withAppendedId(collection, id), name));
            }
        } catch (Exception ignored) { }
        if (rows.isEmpty()) {
            TextView empty = new TextView(this); empty.setText("No recordings yet"); empty.setTextColor(Color.LTGRAY);
            empty.setPadding(0, dp(12), 0, dp(12)); recordings.addView(empty); return;
        }
        for (Row row : rows) {
            LinearLayout item = new LinearLayout(this); item.setGravity(Gravity.CENTER_VERTICAL);
            item.setPadding(dp(12), dp(7), dp(6), dp(7)); item.setBackgroundColor(Color.rgb(30, 36, 48));
            LinearLayout.LayoutParams itemLp = new LinearLayout.LayoutParams(-1, -2); itemLp.topMargin = dp(8);
            TextView name = new TextView(this); name.setText(row.name); name.setTextColor(Color.WHITE); name.setTextSize(13);
            item.addView(name, new LinearLayout.LayoutParams(0, -2, 1));
            Button play = button("Play", 0xff334155); play.setMinWidth(dp(72));
            play.setOnClickListener(v -> play(row.uri)); item.addView(play);
            recordings.addView(item, itemLp);
        }
    }

    private void play(Uri uri) {
        try {
            if (mediaPlayer != null) { mediaPlayer.release(); mediaPlayer = null; }
            mediaPlayer = new MediaPlayer(); mediaPlayer.setDataSource(this, uri);
            mediaPlayer.setOnPreparedListener(MediaPlayer::start);
            mediaPlayer.setOnCompletionListener(mp -> { mp.release(); if (mediaPlayer == mp) mediaPlayer = null; });
            mediaPlayer.prepareAsync(); status.setText("Playing recording…");
        } catch (Exception e) { status.setText("Could not play this recording: " + e.getMessage()); }
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    @Override protected void onDestroy() {
        if (savedReceiver != null) try { unregisterReceiver(savedReceiver); } catch (Exception ignored) { }
        if (mediaPlayer != null) { mediaPlayer.release(); mediaPlayer = null; }
        super.onDestroy();
    }

    private static class Row { final Uri uri; final String name; Row(Uri u, String n) { uri=u; name=n; } }
}
