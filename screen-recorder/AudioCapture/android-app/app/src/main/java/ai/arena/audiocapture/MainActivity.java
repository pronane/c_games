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
import android.widget.EditText;
import android.widget.CheckBox;
import android.widget.ProgressBar;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.graphics.Color;
import android.graphics.Typeface;

import java.util.ArrayList;
import java.util.List;

public class MainActivity extends Activity {
    private static final int REQ_AUDIO = 10;
    private static final int REQ_CAPTURE = 11;
    private static final int REQ_NOTIFICATIONS = 12;
    private static final String ACTION_SAVED = "ai.arena.audiocapture.SAVED";
    private LinearLayout root, recordings;
    private TextView status;
    private Button startButton, stopButton;
    private MediaPlayer mediaPlayer;
    private BroadcastReceiver savedReceiver;
    private EditText urlListInput;
    private List<String> sessionUrls = new ArrayList<>();
    private int currentUrlIndex = -1;
    private boolean launchPlaylistAfterPermission = false;
    private CheckBox autoNextCheck;
    private EditText graceEntry, silenceEntry, thresholdEntry;
    private ProgressBar levelMeter;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        buildUi();
        IntentFilter filter = new IntentFilter(ACTION_SAVED); filter.addAction(CaptureService.ACTION_AUTO_NEXT); filter.addAction(CaptureService.ACTION_LEVEL);
        savedReceiver = new BroadcastReceiver() {
            @Override public void onReceive(Context c, Intent i) {
                if(CaptureService.ACTION_AUTO_NEXT.equals(i.getAction())){status.setText(i.getStringExtra("message"));postNextNotification();return;}
                if(CaptureService.ACTION_LEVEL.equals(i.getAction())){double rms=i.getDoubleExtra("rms",0);levelMeter.setProgress((int)(Math.max(0,Math.min(1,(20*Math.log10(Math.max(rms,1e-6))+60)/60))*1000));status.setText(String.format(java.util.Locale.US,"Recording · input %.1f dBFS",20*Math.log10(Math.max(rms,1e-6))));return;}
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
        TextView urlTitle = new TextView(this); urlTitle.setText("Browser URL playlist (session only)"); urlTitle.setTextColor(Color.WHITE); urlTitle.setTextSize(16); urlTitle.setTypeface(null,Typeface.BOLD); root.addView(urlTitle);
        urlListInput = new EditText(this); urlListInput.setHint("Paste one http(s) URL per line"); urlListInput.setTextColor(Color.WHITE); urlListInput.setHintTextColor(Color.GRAY); urlListInput.setMinLines(2); urlListInput.setMaxLines(4); urlListInput.setGravity(Gravity.TOP); urlListInput.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE|android.text.InputType.TYPE_TEXT_VARIATION_URI); urlListInput.setBackgroundColor(Color.rgb(30,36,48)); root.addView(urlListInput,new LinearLayout.LayoutParams(-1,dp(100)));
        TextView urlNote = new TextView(this); urlNote.setText("URLs are kept in memory only; cookies and sign-in stay in your browser. Android records one combined file. Browser autoplay may require a tap."); urlNote.setTextColor(Color.LTGRAY); urlNote.setTextSize(11); root.addView(urlNote);
        autoNextCheck=new CheckBox(this); autoNextCheck.setText("Notify me after silence (tap notification for next URL)"); autoNextCheck.setTextColor(Color.WHITE); autoNextCheck.setChecked(false); root.addView(autoNextCheck);
        LinearLayout timing=new LinearLayout(this); graceEntry=smallEntry("2:30"); silenceEntry=smallEntry("5"); thresholdEntry=smallEntry("-54"); timing.addView(graceEntry,new LinearLayout.LayoutParams(0,dp(42),1)); timing.addView(silenceEntry,new LinearLayout.LayoutParams(0,dp(42),1)); timing.addView(thresholdEntry,new LinearLayout.LayoutParams(0,dp(42),1)); root.addView(timing);
        TextView timingHint=new TextView(this); timingHint.setText("Grace min:sec · quiet seconds · threshold dBFS. Auto-next is user-confirmed by Android notification."); timingHint.setTextColor(Color.LTGRAY); timingHint.setTextSize(10); root.addView(timingHint);
        LinearLayout playlistButtons = new LinearLayout(this); playlistButtons.setPadding(0,dp(4),0,dp(8));
        Button startList = button("Start URL list",0xff2563eb), nextUrl = button("Next URL",0xff475569);
        playlistButtons.addView(startList,new LinearLayout.LayoutParams(0,dp(46),1)); LinearLayout.LayoutParams nextLp=new LinearLayout.LayoutParams(0,dp(46),1); nextLp.leftMargin=dp(8); playlistButtons.addView(nextUrl,nextLp); root.addView(playlistButtons);
        startList.setOnClickListener(v -> prepareUrlPlaylist()); nextUrl.setOnClickListener(v -> launchNextUrl());
        LinearLayout buttons = new LinearLayout(this); buttons.setOrientation(LinearLayout.HORIZONTAL);
        startButton = button("Start capture", 0xff2563eb); stopButton = button("Stop and save", 0xffb91c1c);
        buttons.addView(startButton, new LinearLayout.LayoutParams(0, dp(52), 1));
        LinearLayout.LayoutParams stopLp = new LinearLayout.LayoutParams(0, dp(52), 1); stopLp.leftMargin = dp(10);
        buttons.addView(stopButton, stopLp); root.addView(buttons);
        status = new TextView(this); status.setText("Ready. Your recordings are saved on this device.");
        status.setTextColor(Color.rgb(134, 239, 172)); status.setTextSize(13); status.setPadding(0, dp(14), 0, dp(8)); root.addView(status);
        levelMeter=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);levelMeter.setMax(1000);levelMeter.setProgress(0);root.addView(levelMeter,new LinearLayout.LayoutParams(-1,dp(8)));
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

    private EditText smallEntry(String hint){EditText e=new EditText(this);e.setHint(hint);e.setText(hint);e.setTextColor(Color.WHITE);e.setHintTextColor(Color.GRAY);e.setSingleLine(true);e.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL|android.text.InputType.TYPE_NUMBER_FLAG_SIGNED);return e;}
    private double parseGrace(){try{String x=graceEntry.getText().toString().trim();double v;if(x.contains(":")){String[] p=x.split(":",2);v=Double.parseDouble(p[0])*60+Double.parseDouble(p[1]);}else v=Double.parseDouble(x);return Math.max(0,Math.min(7200,v));}catch(Exception e){return 150;}}
    private double parsePositive(EditText field,double fallback,double max){try{return Math.max(.5,Math.min(max,Double.parseDouble(field.getText().toString().trim())));}catch(Exception e){return fallback;}}
    private double parseThreshold(){try{return Math.max(-80,Math.min(-20,Double.parseDouble(thresholdEntry.getText().toString().trim())));}catch(Exception e){return -54;}}

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
        else if(request==REQ_NOTIFICATIONS) status.setText(results.length>0&&results[0]==PackageManager.PERMISSION_GRANTED?"Notifications allowed. Tap Start URL list again.":"Notifications denied; silence auto-next reminders will not appear.");
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == REQ_CAPTURE) {
            if (result != RESULT_OK || data == null) { launchPlaylistAfterPermission=false; status.setText("Capture permission was not granted."); return; }
            Intent service = new Intent(this, CaptureService.class)
                    .setAction(CaptureService.ACTION_START)
                    .putExtra(CaptureService.EXTRA_RESULT_CODE, result)
                    .putExtra(CaptureService.EXTRA_RESULT_DATA, data)
                    .putExtra(CaptureService.EXTRA_AUTO_NEXT, autoNextCheck.isChecked())
                    .putExtra(CaptureService.EXTRA_GRACE_SECONDS, parseGrace())
                    .putExtra(CaptureService.EXTRA_SILENCE_SECONDS, parsePositive(silenceEntry,5,120))
                    .putExtra(CaptureService.EXTRA_THRESHOLD_DB, parseThreshold());
            if (Build.VERSION.SDK_INT >= 26) startForegroundService(service); else startService(service);
            status.setText("Recording app playback audio…"); setRecording(true);
            if (launchPlaylistAfterPermission) { launchPlaylistAfterPermission=false; launchCurrentUrl(); }
        }
    }

    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);if(intent.getBooleanExtra("openNextUrl",false)){intent.removeExtra("openNextUrl");launchNextUrl();}}
    private void postNextNotification(){
        if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED){status.setText("Silence detected. Return to Audio Capture and tap Next URL (notifications are not allowed).");return;}
        String channel="url_auto_next";NotificationManager nm=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);if(Build.VERSION.SDK_INT>=26)nm.createNotificationChannel(new NotificationChannel(channel,"URL playlist",NotificationManager.IMPORTANCE_HIGH));
        Intent open=new Intent(this,MainActivity.class).putExtra("openNextUrl",true).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP|Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi=PendingIntent.getActivity(this,812,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder b=Build.VERSION.SDK_INT>=26?new Notification.Builder(this,channel):new Notification.Builder(this);
        b.setSmallIcon(android.R.drawable.ic_media_play).setContentTitle("Silence detected").setContentText("Tap to open the next URL in your list").setContentIntent(pi).setAutoCancel(true).addAction(android.R.drawable.ic_media_play,"Open next URL",pi);
        nm.notify(812,b.build());
    }

    private void prepareUrlPlaylist() {
        sessionUrls.clear(); currentUrlIndex=-1;
        for(String line:urlListInput.getText().toString().split("\\R")) {
            String value=line.trim(); if(value.isEmpty()) continue;
            Uri uri=Uri.parse(value);
            if((!"http".equalsIgnoreCase(uri.getScheme())&&!"https".equalsIgnoreCase(uri.getScheme()))||uri.getHost()==null||uri.getUserInfo()!=null){status.setText("Use complete http(s) URLs without embedded username/password.");return;}
            sessionUrls.add(value);
        }
        if(sessionUrls.isEmpty()){status.setText("Paste at least one http(s) URL first.");return;}
        if(autoNextCheck.isChecked()&&Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED){requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},REQ_NOTIFICATIONS);return;}
        currentUrlIndex=0;
        launchPlaylistAfterPermission=true;
        if(startButton.isEnabled()) requestCapture(); else launchCurrentUrl();
    }
    private void launchCurrentUrl() {
        if(currentUrlIndex<0||currentUrlIndex>=sessionUrls.size()){status.setText("URL list is not active. Start a URL list first.");return;}
        try { Intent view=new Intent(Intent.ACTION_VIEW,Uri.parse(sessionUrls.get(currentUrlIndex))); startActivity(view); status.setText("Opened URL "+(currentUrlIndex+1)+" of "+sessionUrls.size()+" in your browser. Use Next URL to continue."); }
        catch(Exception e){status.setText("Could not open URL in a browser: "+e.getMessage());}
    }
    private void launchNextUrl() {
        if(sessionUrls.isEmpty()){status.setText("Start a URL list first.");return;}
        if(currentUrlIndex+1>=sessionUrls.size()){status.setText("Playlist finished; saving and stopping the combined recording.");if(!startButton.isEnabled())startService(new Intent(this,CaptureService.class).setAction(CaptureService.ACTION_STOP));return;}
        currentUrlIndex++;
        try { startService(new Intent(this,CaptureService.class).setAction(CaptureService.ACTION_URL_ADVANCED)); } catch(Exception ignored) { }
        launchCurrentUrl();
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
            Button edit = button("Edit", 0xff2563eb); edit.setMinWidth(dp(68));
            edit.setOnClickListener(v -> { stopPlayback(); startActivity(new Intent(this, EditorActivity.class).putExtra("uri", row.uri.toString())); });
            LinearLayout.LayoutParams editLp = new LinearLayout.LayoutParams(-2, -2); editLp.leftMargin = dp(5); item.addView(edit, editLp);
            recordings.addView(item, itemLp);
        }
    }

    private void stopPlayback() {
        if (mediaPlayer != null) { try { mediaPlayer.stop(); } catch (Exception ignored) { } mediaPlayer.release(); mediaPlayer = null; }
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
