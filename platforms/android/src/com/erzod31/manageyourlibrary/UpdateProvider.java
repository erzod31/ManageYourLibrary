package com.erzod31.manageyourlibrary;

import android.content.*;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.*;

/** Grants the native installer read access to exactly one verified APK. */
public final class UpdateProvider extends ContentProvider {
    @Override public boolean onCreate() { return true; }
    private File file(Uri uri) throws IOException {
        String name = uri.getLastPathSegment();
        if (uri.getPathSegments().size() != 1 || name == null || !name.matches("[a-f0-9]{64}\\.apk")) throw new FileNotFoundException();
        File root = new File(getContext().getFilesDir(), "updates").getCanonicalFile();
        File file = new File(root, name).getCanonicalFile();
        if (!file.getParentFile().equals(root) || !file.isFile()) throw new FileNotFoundException();
        return file;
    }
    @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("Solo lectura");
        try { return ParcelFileDescriptor.open(file(uri), ParcelFileDescriptor.MODE_READ_ONLY); }
        catch (IOException ex) { throw new FileNotFoundException("Paquete de actualización no disponible"); }
    }
    @Override public String getType(Uri uri) { return "application/vnd.android.package-archive"; }
    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) {
        try {
            File file = file(uri); String[] columns = projection == null ? new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE} : projection;
            MatrixCursor cursor = new MatrixCursor(columns); Object[] values = new Object[columns.length];
            for (int i=0;i<columns.length;i++) values[i] = OpenableColumns.DISPLAY_NAME.equals(columns[i]) ? "ManageYourLibrary-update.apk" : OpenableColumns.SIZE.equals(columns[i]) ? file.length() : null;
            cursor.addRow(values); return cursor;
        } catch (IOException ex) { return null; }
    }
    @Override public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException(); }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) { throw new UnsupportedOperationException(); }
    @Override public int delete(Uri uri, String selection, String[] args) { throw new UnsupportedOperationException(); }
}
