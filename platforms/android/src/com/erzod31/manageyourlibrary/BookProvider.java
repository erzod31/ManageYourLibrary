package com.erzod31.manageyourlibrary;

import android.content.*;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import android.webkit.MimeTypeMap;
import java.io.*;
import java.util.List;

public final class BookProvider extends ContentProvider {
    @Override public boolean onCreate() { return true; }
    private File file(Uri uri) throws FileNotFoundException {
        try {
            List<String> parts = uri.getPathSegments();
            if (parts.size() != 2 || !parts.get(0).matches("[a-f0-9]{32}") || parts.get(1).contains("/") || parts.get(1).contains("\\"))
                throw new FileNotFoundException();
            File root = new File(getContext().getCacheDir(), "books").getCanonicalFile();
            File file = new File(new File(root, parts.get(0)), parts.get(1)).getCanonicalFile();
            if (!file.getPath().startsWith(root.getPath() + File.separator) || !file.isFile()) throw new FileNotFoundException();
            return file;
        } catch (IOException e) { throw new FileNotFoundException("Copia local no disponible"); }
    }
    @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("Solo lectura");
        return ParcelFileDescriptor.open(file(uri), ParcelFileDescriptor.MODE_READ_ONLY);
    }
    @Override public String getType(Uri uri) {
        String extension = MimeTypeMap.getFileExtensionFromUrl(uri.toString());
        String type = MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension.toLowerCase(java.util.Locale.ROOT));
        return type == null ? "application/octet-stream" : type;
    }
    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) {
        try {
            File f = file(uri); String[] columns = projection == null ? new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE} : projection;
            MatrixCursor result = new MatrixCursor(columns); Object[] row = new Object[columns.length];
            for (int i = 0; i < columns.length; i++) row[i] = OpenableColumns.DISPLAY_NAME.equals(columns[i]) ? f.getName() : OpenableColumns.SIZE.equals(columns[i]) ? f.length() : null;
            result.addRow(row); return result;
        } catch (FileNotFoundException e) { return null; }
    }
    @Override public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException(); }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) { throw new UnsupportedOperationException(); }
    @Override public int delete(Uri uri, String selection, String[] args) { throw new UnsupportedOperationException(); }
}
