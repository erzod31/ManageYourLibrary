package com.erzod31.manageyourlibrary;

import android.app.*;
import android.content.*;
import android.content.pm.PackageInfo;
import android.graphics.Bitmap;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import javax.net.ssl.*;
import java.io.*;
import java.net.*;
import java.security.KeyStore;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;

/** QA-only TLS fixture in the emulator; no host service or real installer. */
final class UpdateQa {
    interface Case { void run() throws Exception; }
    static void require(boolean condition,String message){if(!condition)throw new AssertionError(message);}
    static void reject(Case test) throws Exception {boolean refused=false;try{test.run();}catch(Exception expected){refused=true;}require(refused,"Unsafe operation was accepted");}
    static JSONObject cloneJson(JSONObject value)throws Exception{return new JSONObject(value.toString());}
    static void copy(Context context,String asset,File file)throws Exception{try(InputStream in=context.getAssets().open("qa/"+asset);FileOutputStream out=new FileOutputStream(file)){byte[] b=new byte[8192];int n;while((n=in.read(b))!=-1)out.write(b,0,n);out.getFD().sync();}}
    static final class Fixture implements AutoCloseable {
        final SSLServerSocket server;final byte[] apk;volatile JSONObject metadata;volatile boolean offline=false,slow=false;volatile boolean closed=false;
        Fixture(Context context)throws Exception{
            metadata=new JSONObject(DesktopApi.readText(context.getAssets().open("qa/future.update.json"),65536));
            try(InputStream in=context.getAssets().open("qa/future.apk");ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[8192];int n;while((n=in.read(b))!=-1)out.write(b,0,n);apk=out.toByteArray();}
            KeyStore keys=KeyStore.getInstance("PKCS12");try(InputStream in=context.getAssets().open("qa/server.p12")){keys.load(in,"fixture-only".toCharArray());}
            KeyManagerFactory factory=KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());factory.init(keys,"fixture-only".toCharArray());
            SSLContext tls=SSLContext.getInstance("TLS");tls.init(factory.getKeyManagers(),null,null);
            server=(SSLServerSocket)tls.getServerSocketFactory().createServerSocket(0,4,InetAddress.getByName("127.0.0.1"));
            Thread worker=new Thread(()->{while(!closed)try{Socket socket=server.accept();new Thread(()->serve(socket),"UpdateQaRequest").start();}catch(Exception ignored){}} ,"UpdateQaTls");worker.setDaemon(true);worker.start();
        }
        void serve(Socket socket){try(Socket own=socket){own.setSoTimeout(5000);BufferedReader input=new BufferedReader(new InputStreamReader(own.getInputStream(),"US-ASCII"));String first=input.readLine();String line;while((line=input.readLine())!=null&&!line.isEmpty()){}
            boolean file=first!=null&&first.contains("/api/v1/android-update/file");boolean update=first!=null&&first.contains("/api/v1/android-update");
            byte[] body=file?apk:(update?metadata.toString():"{\"books\":[],\"total\":0,\"offset\":0,\"limit\":30}").getBytes("UTF-8");
            if(offline){body="{\"error\":\"Fixture offline\"}".getBytes("UTF-8");}
            OutputStream output=own.getOutputStream();output.write(((offline?"HTTP/1.1 503 Fixture unavailable":"HTTP/1.1 200 OK")+"\r\nContent-Type: "+(file?"application/vnd.android.package-archive":"application/json")+"\r\nContent-Length: "+body.length+"\r\nConnection: close\r\n\r\n").getBytes("US-ASCII"));
            if(slow&&file)Thread.sleep(2500);output.write(body);output.flush();
        }catch(Exception ignored){}}
        public void close()throws IOException{closed=true;server.close();}
    }
    static View find(View root,String label){if(root.getContentDescription()!=null&&label.contentEquals(root.getContentDescription()))return root;if(root instanceof ViewGroup)for(int i=0;i<((ViewGroup)root).getChildCount();i++){View v=find(((ViewGroup)root).getChildAt(i),label);if(v!=null)return v;}return null;}
    static void await(Instrumentation test,MainActivity activity,int id,String contains)throws Exception{
        long deadline=System.currentTimeMillis()+15000;
        while(System.currentTimeMillis()<deadline){AtomicReference<String> text=new AtomicReference<>("");test.runOnMainSync(()->{View view=activity.findViewById(id);if(view instanceof TextView)text.set(((TextView)view).getText().toString());});if(text.get().contains(contains))return;Thread.sleep(100);}
        throw new AssertionError("Missing update status: "+contains);
    }
    static void click(Instrumentation test,MainActivity activity,int id){test.runOnMainSync(()->{View view=activity.findViewById(id);view.requestRectangleOnScreen(new android.graphics.Rect(0,0,view.getWidth(),view.getHeight()),true);view.performClick();});test.waitForIdleSync();}
    static void check(JSONArray checks,String name,Case test)throws Exception{long started=System.nanoTime();test.run();checks.put(new JSONObject().put("name",name).put("passed",true).put("ms",(System.nanoTime()-started)/1000000));}
    static void run(Instrumentation test,MainActivity initial){Context context=initial;JSONObject report=new JSONObject();JSONArray checks=new JSONArray();
        try { report.put("qaAssets",Arrays.toString(context.getAssets().list("qa"))).put("licenseAssets",Arrays.toString(context.getAssets().list("licenses")))
            .put("assetsRoot",Arrays.toString(context.getAssets().list(""))).put("resourcePath",context.getPackageResourcePath())
            .put("styleResource",context.getResources().getResourceName(R.style.AppTheme)); } catch(Exception info){try{report.put("resourceError",info.toString());}catch(Exception ignored){}}
        try(Fixture fixture=new Fixture(context)){
            check(checks,"canonical_assets_and_drawable_are_readable",()->{
                require(DesktopApi.readText(context.getAssets().open("licenses/PROJECT_LICENSE.txt"),65536).contains("MIT License"),"License asset missing");
                require(context.getResources().getDrawable(R.drawable.ic_library,context.getTheme())!=null,"Drawable missing");
            });
            JSONObject metadata=cloneJson(fixture.metadata);String address="https://127.0.0.1:"+fixture.server.getLocalPort();
            DesktopApi api=new DesktopApi(address,"fixture-token-not-a-user-credential",true);AppUpdates updates=new AppUpdates(context);
            File future=new File(context.getFilesDir(),"future-fixture.apk");File wrongSigner=new File(context.getFilesDir(),"wrong-signer-fixture.apk");copy(context,"future.apk",future);copy(context,"wrong-signer.apk",wrongSigner);
            PackageInfo original=updates.installed();String originalVersion=original.versionName;long originalCode=AppUpdates.code(original);
            File book=new File(context.getFilesDir(),"synthetic-book.epub");try(FileOutputStream out=new FileOutputStream(book)){out.write("Synthetic protected original".getBytes("UTF-8"));}String originalHash=DesktopApi.hash(book);
            check(checks,"current_available_and_pc_network_error",()->{
                require(updates.check(api).optBoolean("available"),"Missing future update");
                JSONObject current=cloneJson(metadata);current.put("version",originalVersion).put("versionCode",originalCode);fixture.metadata=current;
                require(!updates.check(api).optBoolean("available"),"Equal version offered as update");fixture.metadata=metadata;
                fixture.offline=true;reject(()->updates.check(api));fixture.offline=false;
            });
            check(checks,"wrong_product_platform_certificate_and_downgrade",()->{
                for(String key:new String[]{"product","platform","packageName","certificateSha256"}){JSONObject bad=cloneJson(metadata);bad.put(key,key.equals("certificateSha256")?new String(new char[64]).replace('\0','0'):"Other");reject(()->updates.validateMetadata(bad,true));}
                JSONObject downgrade=cloneJson(metadata);downgrade.put("version","0.0.1").put("versionCode",1);reject(()->updates.validateMetadata(downgrade,true));
            });
            final File[] downloaded=new File[1];
            check(checks,"verified_https_download_and_real_apk_identity",()->{downloaded[0]=updates.download(api,metadata);updates.verify(downloaded[0],metadata);require(DesktopApi.hash(downloaded[0]).equals(metadata.getString("sha256")),"Hash mismatch");});
            check(checks,"wrong_actual_signer_and_internal_version_rejected",()->{
                JSONObject bad=cloneJson(metadata);bad.put("bytes",wrongSigner.length()).put("sha256",DesktopApi.hash(wrongSigner));reject(()->updates.verify(wrongSigner,bad));
                File own=new File(context.getApplicationInfo().sourceDir);JSONObject old=cloneJson(metadata);old.put("bytes",own.length()).put("sha256",DesktopApi.hash(own));reject(()->updates.verify(own,old));
                JSONObject wrongHash=cloneJson(metadata);wrongHash.put("sha256",new String(new char[64]).replace('\0','0'));reject(()->updates.verify(future,wrongHash));
            });
            check(checks,"explicit_confirmation_and_native_install_request_faked",()->{
                List<Intent> calls=new ArrayList<>();AppUpdates.Launcher fake=(intent,request)->calls.add(intent);
                reject(()->updates.handoff(downloaded[0],metadata,false,true,fake));require(calls.isEmpty(),"Install requested without confirmation");
                updates.handoff(downloaded[0],metadata,true,false,fake);require(calls.size()==1&&android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES.equals(calls.get(0).getAction()),"Missing Android install-source authorization");calls.clear();
                updates.handoff(downloaded[0],metadata,true,true,fake);require(calls.size()==1&&Intent.ACTION_INSTALL_PACKAGE.equals(calls.get(0).getAction()),"Native installer was not requested");
                require((calls.get(0).getFlags()&Intent.FLAG_GRANT_READ_URI_PERMISSION)!=0,"No read-only URI grant");
                try(InputStream in=context.getContentResolver().openInputStream(calls.get(0).getData())){require(in!=null&&in.read()=='P',"Installer cannot read verified APK");}
            });
            check(checks,"cancelled_and_interrupted_download_leave_installed_app_unchanged",()->{
                updates.cancel();reject(()->updates.download(api,metadata));updates.cancelled.set(false);
                require(downloaded[0].delete(),"Could not reset QA download");fixture.slow=true;
                Thread cancel=new Thread(()->{try{Thread.sleep(150);}catch(Exception ignored){}updates.cancel();});cancel.start();reject(()->updates.download(api,metadata));cancel.join();fixture.slow=false;updates.cancelled.set(false);
                File[] leftovers=updates.directory.listFiles((dir,name)->name.endsWith(".part"));require(leftovers==null||leftovers.length==0,"Partial APK left as usable update");
            });
            SecretStore store=new SecretStore(context);store.save(address,"fixture-token-not-a-user-credential");
            Instrumentation.ActivityMonitor monitor=test.addMonitor(MainActivity.class.getName(),null,false);
            test.runOnMainSync(initial::recreate);
            MainActivity activity=(MainActivity)monitor.waitForActivityWithTimeout(8000);test.removeMonitor(monitor);
            require(activity!=null,"Could not reopen QA activity with the fixture connection");
            check(checks,"native_update_settings_ui_check_download_and_confirmation",()->{
                test.runOnMainSync(()->{View tab=find(activity.getWindow().getDecorView(),"Conexión");require(tab!=null,"Missing settings tab");tab.performClick();});test.waitForIdleSync();
                click(test,activity,802);await(test,activity,801,"Disponible:");click(test,activity,803);await(test,activity,801,"APK verificado");
                click(test,activity,804);Thread.sleep(300);Bitmap image=test.getUiAutomation().takeScreenshot();
                try(FileOutputStream out=new FileOutputStream(new File(context.getFilesDir(),"dg0020-update-confirmation.png"))){image.compress(Bitmap.CompressFormat.PNG,100,out);}image.recycle();
                test.sendKeyDownUpSync(KeyEvent.KEYCODE_BACK); // Cancel app confirmation; no real native installer.
            });
            check(checks,"version_certificate_connection_and_original_preserved",()->{
                require(originalCode==AppUpdates.code(updates.installed())&&originalVersion.equals(updates.installed().versionName),"A real update happened during QA");require(originalHash.equals(DesktopApi.hash(book)),"Original changed");require(store.token().equals("fixture-token-not-a-user-credential"),"Connection lost");
            });
            report.put("passed",true);
        }catch(Throwable failure){try{report.put("passed",false).put("error",failure.toString());StringWriter trace=new StringWriter();failure.printStackTrace(new PrintWriter(trace));report.put("trace",trace.toString());}catch(Exception ignored){}}
        finally{try{report.put("checks",checks).put("nativeInstallationsApplied",false).put("realInstallerExecuted",false).put("launcher","fake").put("hostNetworkServicesChanged",false).put("api",Build.VERSION.SDK_INT);
            try(FileOutputStream out=new FileOutputStream(new File(context.getFilesDir(),"dg0020-updates.json"))){out.write(report.toString(2).getBytes("UTF-8"));}
            Bundle result=new Bundle();result.putString("DG-0020",report.toString());test.finish(report.optBoolean("passed")?Activity.RESULT_OK:Activity.RESULT_CANCELED,result);
        }catch(Exception failure){test.finish(Activity.RESULT_CANCELED,new Bundle());}}
    }
}
