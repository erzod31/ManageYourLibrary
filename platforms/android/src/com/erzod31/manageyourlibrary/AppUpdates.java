package com.erzod31.manageyourlibrary;

import android.app.Activity;
import android.content.*;
import android.content.pm.*;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import org.json.JSONObject;
import java.io.*;
import java.net.HttpURLConnection;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** Private PC channel plus native package/signature checks, never a browser link updater. */
final class AppUpdates {
    static final int INSTALL_REQUEST = 901;
    static final int SETTINGS_REQUEST = 902;
    static final long MAX_APK = 128L * 1024 * 1024;
    interface Launcher { void launch(Intent intent, int request) throws Exception; }
    final Context context;
    final File directory;
    final AtomicBoolean cancelled = new AtomicBoolean();
    private volatile HttpURLConnection active;
    AppUpdates(Context context) {
        this.context = context; directory = new File(context.getFilesDir(), "updates");
    }
    void cancel() { cancelled.set(true); HttpURLConnection connection = active; if (connection != null) connection.disconnect(); }
    private void checkCancelled() throws InterruptedIOException {
        if (cancelled.get() || Thread.currentThread().isInterrupted()) throw new InterruptedIOException("Actualización cancelada; la versión instalada se conserva");
    }
    PackageInfo installed() throws Exception {
        return context.getPackageManager().getPackageInfo(context.getPackageName(), Build.VERSION.SDK_INT >= 28 ? PackageManager.GET_SIGNING_CERTIFICATES : PackageManager.GET_SIGNATURES);
    }
    static long code(PackageInfo info) { return Build.VERSION.SDK_INT >= 28 ? info.getLongVersionCode() : info.versionCode; }
    static int[] version(String text) throws IOException {
        if (text == null || !text.matches("(0|[1-9][0-9]{0,5})\\.(0|[1-9][0-9]{0,5})\\.(0|[1-9][0-9]{0,5})")) throw new IOException("Versión no válida");
        String[] parts = text.split("\\."); return new int[]{Integer.parseInt(parts[0]),Integer.parseInt(parts[1]),Integer.parseInt(parts[2])};
    }
    static int compare(String left, String right) throws IOException {
        int[] a=version(left), b=version(right); for(int i=0;i<3;i++) if(a[i]!=b[i]) return Integer.compare(a[i],b[i]); return 0;
    }
    JSONObject check(DesktopApi client) throws Exception {
        checkCancelled();
        JSONObject value;
        try { value = client.request("GET", "/api/v1/android-update", null); }
        catch (IOException ex) { throw new IOException("No se pudo consultar el canal de actualización. Comprueba Tailscale y usa el escritorio 0.5.5 o posterior.",ex); }
        checkCancelled();
        validateMetadata(value, false);
        value.put("available", compare(value.getString("version"),installed().versionName)>0 && value.getLong("versionCode")>code(installed()));
        return value;
    }
    void validateMetadata(JSONObject value, boolean newer) throws Exception {
        PackageInfo current=installed(); String version=value.getString("version"); AppUpdates.version(version);
        if (!"ManageYourLibrary".equals(value.optString("product")) || !"android-universal".equals(value.optString("platform")) ||
            !context.getPackageName().equals(value.optString("packageName")) || value.optInt("schema")!=1 ||
            !value.optString("sha256").matches("[a-f0-9]{64}") || !value.optString("certificateSha256").matches("[a-f0-9]{64}") ||
            value.optLong("bytes")<=0 || value.optLong("bytes")>MAX_APK || value.optInt("minSdk")<26 || value.optInt("minSdk")>Build.VERSION.SDK_INT)
            throw new IOException("El PC ofreció un paquete de otro producto/plataforma o sin datos de verificación válidos");
        if (!Arrays.asList(signers(current)).contains(value.getString("certificateSha256"))) throw new IOException("El certificado del canal no coincide con la aplicación instalada");
        if (newer && (compare(version,current.versionName)<=0 || value.getLong("versionCode")<=code(current))) throw new IOException("No se permite instalar una versión anterior o igual");
    }
    static String[] signers(PackageInfo info) throws Exception {
        Signature[] signatures = Build.VERSION.SDK_INT >= 28 && info.signingInfo != null ? info.signingInfo.getApkContentsSigners() : info.signatures;
        if(signatures==null || signatures.length==0) throw new IOException("No se pudo verificar la firma del paquete");
        String[] result=new String[signatures.length]; for(int i=0;i<signatures.length;i++) result[i]=DesktopApi.hex(MessageDigest.getInstance("SHA-256").digest(signatures[i].toByteArray()));
        Arrays.sort(result); return result;
    }
    File download(DesktopApi client, JSONObject metadata) throws Exception {
        validateMetadata(metadata,true); checkCancelled();
        directory.mkdirs(); File destination=new File(directory,metadata.getString("sha256")+".apk");
        if(destination.isFile()) { verify(destination,metadata); return destination; }
        File temporary=new File(directory,UUID.randomUUID().toString()+".part");
        HttpURLConnection connection=client.connection("GET","/api/v1/android-update/file"); active=connection;
        try {
            if(connection.getResponseCode()!=200) throw new IOException("El PC no pudo entregar la actualización. Comprueba su versión y conexión.");
            long length=metadata.getLong("bytes");
            if(connection.getContentLengthLong()!=length) throw new IOException("El tamaño del APK no coincide con el canal");
            if(directory.getUsableSpace()<length+16L*1024*1024) throw new IOException("Falta espacio para preparar la actualización");
            long count=0;
            try(InputStream input=connection.getInputStream(); FileOutputStream output=new FileOutputStream(temporary)) {
                byte[] buffer=new byte[65536];int n;
                while((n=input.read(buffer))!=-1) {checkCancelled();count+=n;if(count>length) throw new IOException("El paquete supera su tamaño autorizado");output.write(buffer,0,n);}
                output.getFD().sync();
            }
            checkCancelled(); if(count!=length) throw new IOException("Descarga incompleta"); verify(temporary,metadata);
            if(!temporary.renameTo(destination)) throw new IOException("No se pudo conservar el APK verificado");
            save(metadata,destination,"verified"); return destination;
        } finally { connection.disconnect(); if(active==connection)active=null; if(temporary.exists())temporary.delete(); }
    }
    void verify(File apk, JSONObject metadata) throws Exception {
        validateMetadata(metadata,true);
        if(!apk.isFile() || apk.length()!=metadata.getLong("bytes") || !DesktopApi.hash(apk).equals(metadata.getString("sha256"))) throw new IOException("El APK está incompleto o cambió su SHA-256");
        PackageInfo archive=context.getPackageManager().getPackageArchiveInfo(apk.getAbsolutePath(),Build.VERSION.SDK_INT>=28?PackageManager.GET_SIGNING_CERTIFICATES:PackageManager.GET_SIGNATURES);
        PackageInfo current=installed();
        if(archive==null || archive.applicationInfo==null || archive.applicationInfo.minSdkVersion!=metadata.getInt("minSdk") || archive.applicationInfo.minSdkVersion>Build.VERSION.SDK_INT || !current.packageName.equals(archive.packageName) || !metadata.getString("version").equals(archive.versionName) || metadata.getLong("versionCode")!=code(archive)) throw new IOException("La identidad, SDK o versión interna del APK no coincide");
        String[] incoming=signers(archive), previous=signers(current);
        if(!Arrays.equals(incoming,previous) || !Arrays.asList(incoming).contains(metadata.getString("certificateSha256"))) throw new IOException("La actualización no conserva el certificado de la aplicación instalada");
    }
    Intent installIntent(File apk, JSONObject metadata) throws Exception {
        verify(apk,metadata);
        Uri uri=new Uri.Builder().scheme("content").authority(context.getPackageName()+".updates").appendPath(metadata.getString("sha256")+".apk").build();
        Intent intent=new Intent(Intent.ACTION_INSTALL_PACKAGE).setDataAndType(uri,"application/vnd.android.package-archive");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION); intent.setClipData(ClipData.newRawUri("Actualización verificada",uri));
        intent.putExtra(Intent.EXTRA_RETURN_RESULT,true); return intent;
    }
    void handoff(File apk, JSONObject metadata, boolean confirmed, boolean canInstall, Launcher launcher) throws Exception {
        if(!confirmed)throw new IOException("La instalación requiere confirmación explícita");
        verify(apk,metadata); checkCancelled();
        if(!canInstall) {
            save(metadata,apk,"permission_needed");
            launcher.launch(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+context.getPackageName())),SETTINGS_REQUEST); return;
        }
        Intent intent=installIntent(apk,metadata);save(metadata,apk,"native_confirmation_requested");launcher.launch(intent,INSTALL_REQUEST);
    }
    void save(JSONObject metadata,File apk,String state) throws Exception {
        directory.mkdirs(); JSONObject record=new JSONObject().put("metadata",metadata).put("file",apk.getName()).put("state",state);
        File temporary=new File(directory,"pending.writing"), destination=new File(directory,"pending.json");
        try(FileOutputStream out=new FileOutputStream(temporary)){out.write(record.toString().getBytes("UTF-8"));out.getFD().sync();}
        if(!temporary.renameTo(destination))throw new IOException("No se pudo guardar el estado de actualización");
    }
    JSONObject pending() throws Exception {
        File file=new File(directory,"pending.json");if(!file.isFile())return null;
        JSONObject value=new JSONObject(DesktopApi.readText(new FileInputStream(file),65536));
        String name=value.optString("file");if(!name.matches("[a-f0-9]{64}\\.apk"))throw new IOException("Registro de actualización no válido");
        return value;
    }
}
