package ai.arena.audiocapture;

import android.app.Activity;
import android.content.ContentValues;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.provider.MediaStore;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.view.ViewGroup;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.RandomAccessFile;
import java.util.ArrayList;
import java.util.List;

/** Non-destructive PCM WAV editor for Android recordings. */
public class EditorActivity extends Activity {
    private static final int SCALE = 10000;
    private Uri sourceUri;
    private File pcmFile;
    private long dataOffset = 44, dataBytes;
    private int rate = 48000, channels = 2, bits = 16, bytesPerFrame = 4;
    private List<long[]> segments = new ArrayList<>();
    private final List<List<long[]>> undo = new ArrayList<>(), redo = new ArrayList<>();
    private SeekBar startBar, endBar;
    private TextView rangeText, status;
    private WaveView wave;
    private MediaPlayer player;
    private final List<double[]> breakCandidates = new ArrayList<>();
    private int breakIndex = -1;
    private final Handler handler = new Handler();
    private double duration() { long frames=0; for (long[] s:segments) frames += s[1]-s[0]; return (double)frames/rate; }
    private int dp(int n) { return Math.round(n*getResources().getDisplayMetrics().density); }

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        sourceUri = Uri.parse(getIntent().getStringExtra("uri"));
        try { prepareSource(); } catch (Exception e) { finish(); return; }
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(18),dp(20),dp(18),dp(16)); root.setBackgroundColor(Color.rgb(18,21,28));
        ScrollView scroll = new ScrollView(this); scroll.addView(root); setContentView(scroll);
        TextView title = text("Edit recording",22,Color.WHITE,true); root.addView(title);
        TextView help = text("Adjust the two handles to select audio. Trim keeps the selection; Remove cuts it out. The original is never changed.",13,Color.LTGRAY,false);
        help.setPadding(0,dp(8),0,dp(10)); root.addView(help);
        wave = new WaveView(); LinearLayout.LayoutParams wp = new LinearLayout.LayoutParams(-1,dp(150)); root.addView(wave,wp);
        rangeText=text("Selection",14,Color.WHITE,true); rangeText.setPadding(0,dp(10),0,dp(4)); root.addView(rangeText);
        startBar = new SeekBar(this); endBar = new SeekBar(this);
        startBar.setMax(SCALE); endBar.setMax(SCALE); startBar.setProgress(0); endBar.setProgress(SCALE);
        root.addView(label("Start")); root.addView(startBar); root.addView(label("End")); root.addView(endBar);
        SeekBar.OnSeekBarChangeListener changed = new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar s,int p,boolean user) { updateRange(); wave.invalidate(); }
            public void onStartTrackingTouch(SeekBar s) {} public void onStopTrackingTouch(SeekBar s) {}
        };
        startBar.setOnSeekBarChangeListener(changed); endBar.setOnSeekBarChangeListener(changed);
        LinearLayout previewRow = new LinearLayout(this); previewRow.setGravity(Gravity.CENTER_VERTICAL);
        Button preview = button("Preview range",0xff334155); previewRow.addView(preview,new LinearLayout.LayoutParams(0,dp(46),1));
        Button stop = button("Stop preview",0xff475569); LinearLayout.LayoutParams stp=new LinearLayout.LayoutParams(0,dp(46),1); stp.leftMargin=dp(8); previewRow.addView(stop,stp); root.addView(previewRow);
        preview.setOnClickListener(v -> previewSelection()); stop.setOnClickListener(v -> stopPlayer());
        LinearLayout editRow=new LinearLayout(this); editRow.setPadding(0,dp(10),0,0);
        Button trim=button("Trim to selection",0xff2563eb), remove=button("Remove selection",0xff475569);
        editRow.addView(trim,new LinearLayout.LayoutParams(0,dp(48),1)); LinearLayout.LayoutParams rp=new LinearLayout.LayoutParams(0,dp(48),1); rp.leftMargin=dp(8); editRow.addView(remove,rp); root.addView(editRow);
        trim.setOnClickListener(v -> apply("trim")); remove.setOnClickListener(v -> apply("remove"));
        LinearLayout history=new LinearLayout(this); history.setPadding(0,dp(8),0,0);
        Button u=button("Undo",0xff334155), r=button("Redo",0xff334155);
        history.addView(u,new LinearLayout.LayoutParams(0,dp(44),1)); LinearLayout.LayoutParams rlp=new LinearLayout.LayoutParams(0,dp(44),1); rlp.leftMargin=dp(8); history.addView(r,rlp); root.addView(history);
        u.setOnClickListener(v -> history(false)); r.setOnClickListener(v -> history(true));
        Button breaks=button("Find possible ad breaks",0xff92400e); LinearLayout.LayoutParams blp=new LinearLayout.LayoutParams(-1,dp(46)); blp.topMargin=dp(8); root.addView(breaks,blp); breaks.setOnClickListener(v -> findBreak());
        Button save=button("Save edited copy",0xff15803d); LinearLayout.LayoutParams slp=new LinearLayout.LayoutParams(-1,dp(50)); slp.topMargin=dp(10); root.addView(save,slp);
        save.setOnClickListener(v -> saveCopy());
        status=text("Original preserved. Edits apply to a new copy.",12,0xff86efac,false); status.setPadding(0,dp(8),0,0); root.addView(status);
        updateRange();
    }

    private TextView text(String s,int size,int color,boolean bold) { TextView t=new TextView(this); t.setText(s); t.setTextSize(size); t.setTextColor(color); if(bold)t.setTypeface(null,android.graphics.Typeface.BOLD); return t; }
    private TextView label(String s) { TextView t=text(s,12,0xff94a3b8,false); t.setPadding(0,dp(4),0,0); return t; }
    private Button button(String s,int color) { Button b=new Button(this); b.setText(s); b.setTextColor(Color.WHITE); b.setAllCaps(false); b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(color)); return b; }
    private void prepareSource() throws Exception {
        pcmFile=new File(getCacheDir(),"editor-"+System.currentTimeMillis()+".wav");
        try(FileInputStream in=(FileInputStream)getContentResolver().openInputStream(sourceUri); FileOutputStream out=new FileOutputStream(pcmFile)) {
            byte[] buf=new byte[65536]; int n; while((n=in.read(buf))>0) out.write(buf,0,n);
        }
        try(RandomAccessFile f=new RandomAccessFile(pcmFile,"r")) {
            byte[] h=new byte[44]; f.readFully(h);
            if(h[0]!='R'||h[1]!='I'||h[2]!='F'||h[3]!='F'||h[8]!='W'||h[9]!='A'||h[10]!='V'||h[11]!='E') throw new Exception("Only PCM WAV recordings can be edited on this version.");
            channels=u16(h,22); rate=i32(h,24); bits=u16(h,34); dataOffset=44; dataBytes=f.length()-dataOffset;
            bytesPerFrame=channels*Math.max(1,bits/8);
            if(channels<1||rate<1||bits!=16||dataBytes<=0) throw new Exception("Unsupported or empty WAV file.");
        }
        segments.add(new long[]{0,dataBytes/bytesPerFrame});
    }
    private static int u16(byte[] b,int p){return (b[p]&255)|((b[p+1]&255)<<8);}
    private static int i32(byte[] b,int p){return (b[p]&255)|((b[p+1]&255)<<8)|((b[p+2]&255)<<16)|(b[p+3]<<24);}
    private double start(){return startBar.getProgress()/(double)SCALE*duration();}
    private double end(){return endBar.getProgress()/(double)SCALE*duration();}
    private void updateRange(){if(rangeText!=null)rangeText.setText(String.format(java.util.Locale.US,"Selection: %.2f s – %.2f s   ·   current length %.2f s",start(),end(),duration()));}
    private List<long[]> extract(long from,long to){List<long[]> out=new ArrayList<>(); long pos=0; for(long[] s:segments){long lo=Math.max(from,pos),hi=Math.min(to,pos+s[1]-s[0]); if(hi>lo)out.add(new long[]{s[0]+lo-pos,s[0]+hi-pos}); pos+=s[1]-s[0];} return out;}
    private void apply(String kind){ long total=Math.round(duration()*rate),a=Math.round(start()*rate),b=Math.round(end()*rate); if(b<=a){status.setText("Choose a selection longer than zero.");return;} if(kind.equals("trim")){List<long[]> next=extract(a,b); if(next.isEmpty())return; commit(next);}else{List<long[]> next=extract(0,a); next.addAll(extract(b,total)); if(next.isEmpty()){status.setText("A cut cannot remove the entire recording.");return;} commit(next);} startBar.setProgress(0);endBar.setProgress(SCALE); updateRange();wave.invalidate();status.setText("Edit applied. Undo/Redo are available; source remains unchanged."); }
    private void commit(List<long[]> next){undo.add(copy(segments)); redo.clear(); segments=next;}
    private List<long[]> copy(List<long[]> in){List<long[]> out=new ArrayList<>();for(long[] s:in)out.add(s.clone());return out;}
    private void history(boolean redoAction){List<List<long[]>> from=redoAction?redo:undo,to=redoAction?undo:redo;if(from.isEmpty())return;to.add(copy(segments));segments=from.remove(from.size()-1);startBar.setProgress(0);endBar.setProgress(SCALE);updateRange();wave.invalidate();}
    private void previewSelection(){try{stopPlayer();player=new MediaPlayer();player.setDataSource(this,sourceUri);player.setOnPreparedListener(mp->{mp.seekTo((int)(start()*1000));mp.start();handler.postDelayed(()->{if(player==mp)stopPlayer();},Math.max(100,(long)((end()-start())*1000)));});player.prepareAsync();}catch(Exception e){status.setText("Preview unavailable: "+e.getMessage());}}
    private void stopPlayer(){handler.removeCallbacksAndMessages(null);if(player!=null){try{player.stop();}catch(Exception ignored){}player.release();player=null;}}
    private void findBreak(){
        if(!breakCandidates.isEmpty()){breakIndex=(breakIndex+1)%breakCandidates.size();selectBreak();return;}
        status.setText("Scanning for abrupt loudness changes (review-only)…");
        new Thread(()->{List<double[]> found=new ArrayList<>();try(RandomAccessFile f=new RandomAccessFile(pcmFile,"r")){long total=segments.stream().mapToLong(s->s[1]-s[0]).sum();int win=rate;double previous=Double.NaN;List<Double> levels=new ArrayList<>();List<Double> times=new ArrayList<>();for(long logical=0;logical<total;logical+=win){int count=(int)Math.min(win,total-logical);long[] src=mapCurrent(logical);if(src==null)continue;f.seek(dataOffset+src[0]*bytesPerFrame);long sum=0;long samples=(long)count*channels;for(long j=0;j<samples;j++){int lo=f.read(),hi=f.read();if(lo<0||hi<0)break;short val=(short)((hi<<8)|(lo&255));sum+=(long)val*val;}double rms=Math.sqrt(sum/(double)Math.max(1,samples))/32768.0;levels.add(20*Math.log10(Math.max(rms,1e-6)));times.add((logical+count/2.0)/rate);}for(int i=1;i<levels.size();i++){double a=levels.get(i-1),b=levels.get(i),point=(times.get(i-1)+times.get(i))/2;if(Math.min(a,b)>-45&&Math.abs(a-b)>=12&&(found.isEmpty()||point-found.get(found.size()-1)[0]>=8))found.add(new double[]{Math.max(0,point-2),Math.min(duration(),point+2)});}}catch(Exception ignored){}runOnUiThread(()->{breakCandidates.clear();breakCandidates.addAll(found);breakIndex=found.isEmpty()?-1:0;if(found.isEmpty())status.setText("No loudness changes found. This is not ad recognition.");else selectBreak();});}).start();
    }
    private long[] mapCurrent(long logical){long p=0;for(long[] s:segments){long n=s[1]-s[0];if(logical<p+n)return new long[]{s[0]+logical-p,0};p+=n;}return null;}
    private void selectBreak(){double[] r=breakCandidates.get(breakIndex);startBar.setProgress((int)(r[0]/Math.max(.01,duration())*SCALE));endBar.setProgress((int)(r[1]/Math.max(.01,duration())*SCALE));updateRange();wave.invalidate();status.setText("Possible break "+(breakIndex+1)+"/"+breakCandidates.size()+" — review/preview; loudness-only hint, not ad recognition.");}
    private void saveCopy(){new Thread(()->{try{String name="AudioCapture-edited-"+System.currentTimeMillis()+".wav";ContentValues v=new ContentValues();v.put(MediaStore.Audio.Media.DISPLAY_NAME,name);v.put(MediaStore.Audio.Media.MIME_TYPE,"audio/wav");v.put(MediaStore.Audio.Media.RELATIVE_PATH,Environment.DIRECTORY_MUSIC+"/Audio Capture");if(Build.VERSION.SDK_INT>=29)v.put(MediaStore.Audio.Media.IS_PENDING,1);Uri outUri=getContentResolver().insert(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI,v);if(outUri==null)throw new Exception("Could not create output file");long frames=0;for(long[] s:segments)frames+=s[1]-s[0];long bytes=frames*bytesPerFrame;try(RandomAccessFile in=new RandomAccessFile(pcmFile,"r");java.io.OutputStream out=getContentResolver().openOutputStream(outUri,"w")){writeHeader(out,bytes,rate,channels,bits);byte[] buf=new byte[65536];for(long[] seg:segments){in.seek(dataOffset+seg[0]*bytesPerFrame);long left=(seg[1]-seg[0])*bytesPerFrame;while(left>0){int n=in.read(buf,0,(int)Math.min(buf.length,left));if(n<0)throw new Exception("Unexpected end of source");out.write(buf,0,n);left-=n;}}out.flush();}if(Build.VERSION.SDK_INT>=29){ContentValues done=new ContentValues();done.put(MediaStore.Audio.Media.IS_PENDING,0);getContentResolver().update(outUri,done,null,null);}runOnUiThread(()->{status.setText("Saved edited copy: "+name);});}catch(Exception e){runOnUiThread(()->status.setText("Save failed: "+e.getMessage()));}}).start();}
    private static void writeHeader(java.io.OutputStream o,long bytes,int rate,int ch,int bits)throws Exception{int block=ch*bits/8;writeAscii(o,"RIFF");le32(o,(int)(36+bytes));writeAscii(o,"WAVEfmt ");le32(o,16);le16(o,1);le16(o,ch);le32(o,rate);le32(o,rate*block);le16(o,block);le16(o,bits);writeAscii(o,"data");le32(o,(int)bytes);}
    private static void writeAscii(java.io.OutputStream o,String s)throws Exception{o.write(s.getBytes(java.nio.charset.StandardCharsets.US_ASCII));} private static void le16(java.io.OutputStream o,int v)throws Exception{o.write(v&255);o.write((v>>8)&255);} private static void le32(java.io.OutputStream o,int v)throws Exception{o.write(v&255);o.write((v>>8)&255);o.write((v>>16)&255);o.write((v>>24)&255);}
    @Override protected void onDestroy(){stopPlayer();if(pcmFile!=null)pcmFile.delete();super.onDestroy();}

    private class WaveView extends View {
        private final Paint paint=new Paint(3);
        WaveView(){super(EditorActivity.this);setBackgroundColor(Color.rgb(15,19,26));}
        @Override protected void onDraw(Canvas c){super.onDraw(c);float mid=getHeight()/2f;c.drawLine(0,mid,getWidth(),mid,paintLine(0xff344052,1));paint.setColor(0xff60a5fa);int columns=Math.max(1,getWidth()/3);try(RandomAccessFile f=new RandomAccessFile(pcmFile,"r")){long total=segments.stream().mapToLong(s->s[1]-s[0]).sum();for(int i=0;i<columns;i++){long logical=(long)i*total/columns;long[] src=map(logical);if(src==null)continue;f.seek(dataOffset+src[0]*bytesPerFrame);int sample=0;for(int ch=0;ch<channels;ch++){int lo=f.read(),hi=f.read();if(lo<0||hi<0)break;short value=(short)((hi<<8)|(lo&255));sample=Math.max(sample,Math.abs((int)value));}float amp=sample/32768f*(getHeight()/2f-8);float x=(i+.5f)*getWidth()/columns;c.drawLine(x,mid-amp,x,mid+amp,paint);}}catch(Exception ignored){}paint.setColor(0x443b82f6);c.drawRect((float)(start()/Math.max(.01,duration())*getWidth()),0,(float)(end()/Math.max(.01,duration())*getWidth()),getHeight(),paint);}
        private long[] map(long logical){long p=0;for(long[] s:segments){long n=s[1]-s[0];if(logical<p+n)return new long[]{s[0]+logical-p,0};p+=n;}return null;}
        private Paint paintLine(int color,float width){paint.setColor(color);paint.setStrokeWidth(width);return paint;}
    }
}
