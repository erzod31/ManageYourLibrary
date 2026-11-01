package com.erzod31.manageyourlibrary;

import org.json.JSONObject;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

final class DesktopApi {
    static final long MAX_FILE = 512L * 1024 * 1024;
    final String base;
    final String token;
    private volatile HttpURLConnection activeTransfer;
    void cancelTransfers() {
        HttpURLConnection current = activeTransfer;
        if (current != null) current.disconnect();
    }
    DesktopApi(String base, String token, boolean testing) throws Exception {
        this.base = validateAddress(base, testing); this.token = token;
    }
    static String validateAddress(String text, boolean testing) throws Exception {
        URI uri = new URI(text.trim());
        String host = uri.getHost();
        boolean localTest = testing && ("10.0.2.2".equals(host) || "127.0.0.1".equals(host) || "localhost".equals(host));
        if (!"https".equalsIgnoreCase(uri.getScheme()) || host == null ||
            !(host.toLowerCase(java.util.Locale.ROOT).endsWith(".ts.net") || localTest) || uri.getUserInfo() != null ||
            uri.getQuery() != null || uri.getFragment() != null ||
            !(uri.getPath() == null || uri.getPath().isEmpty() || "/".equals(uri.getPath())) || uri.getPort() == 0 || uri.getPort() > 65535)
            throw new IllegalArgumentException("Copia la dirección HTTPS de Tailscale que muestra el PC, sin rutas ni códigos añadidos.");
        return new URI("https", null, host, uri.getPort(), null, null, null).toASCIIString();
    }
    HttpURLConnection connection(String method, String path) throws Exception {
        if (!path.startsWith("/api/v1/") || path.contains("\r") || path.contains("\n")) throw new IOException("Ruta no válida");
        HttpURLConnection c = (HttpURLConnection) new URL(base + path).openConnection();
        c.setInstanceFollowRedirects(false); c.setRequestMethod(method);
        c.setConnectTimeout(12000); c.setReadTimeout(30000);
        c.setRequestProperty("Accept", "application/json"); c.setRequestProperty("Cache-Control", "no-store");
        if (!token.isEmpty()) c.setRequestProperty("Authorization", "Bearer " + token);
        return c;
    }
    JSONObject request(String method, String path, JSONObject body) throws Exception {
        HttpURLConnection c = connection(method, path);
        try {
            if (body != null) {
                byte[] raw = body.toString().getBytes(StandardCharsets.UTF_8);
                c.setDoOutput(true); c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                c.setFixedLengthStreamingMode(raw.length);
                try (OutputStream out = c.getOutputStream()) { out.write(raw); }
            }
            int status = c.getResponseCode();
            String raw = readText(status >= 200 && status < 300 ? c.getInputStream() : c.getErrorStream(), 2 * 1024 * 1024);
            JSONObject value;
            try { value = new JSONObject(raw); } catch (Exception ex) { throw new IOException("El PC no respondió con el protocolo esperado."); }
            if (status < 200 || status >= 300) throw new IOException(value.optString("error", "Error de conexión: " + status));
            return value;
        } finally { c.disconnect(); }
    }
    static String readText(InputStream stream, int maximum) throws Exception {
        if (stream == null) return "{}";
        try (InputStream input = stream; ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192]; int count;
            while ((count = input.read(buffer)) != -1) {
                if (Thread.currentThread().isInterrupted()) throw new InterruptedIOException("Cancelado");
                if (output.size() + count > maximum) throw new IOException("Respuesta demasiado grande");
                output.write(buffer, 0, count);
            }
            return output.toString("UTF-8");
        }
    }
    byte[] cover(String id) throws Exception {
        HttpURLConnection c = connection("GET", "/api/v1/books/" + id + "/cover");
        try {
            if (c.getResponseCode() != 200) return null;
            try (InputStream in = c.getInputStream(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[8192]; int count;
                while ((count = in.read(buffer)) != -1) {
                    if (out.size() + count > 1024 * 1024) throw new IOException("Portada demasiado grande");
                    out.write(buffer, 0, count);
                }
                return out.toByteArray();
            }
        } finally { c.disconnect(); }
    }
    static String hash(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream in = new FileInputStream(file)) {
            byte[] buffer = new byte[65536]; int count;
            while ((count = in.read(buffer)) != -1) {
                if (Thread.currentThread().isInterrupted()) throw new InterruptedIOException("Cancelado");
                digest.update(buffer, 0, count);
            }
        }
        return hex(digest.digest());
    }
    static String hex(byte[] bytes) {
        StringBuilder value = new StringBuilder();
        for (byte b : bytes) value.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
        return value.toString();
    }
    static long cacheBytes(File folder) {
        long bytes = 0; File[] children = folder.listFiles();
        if (children != null) for (File child : children) bytes += child.isDirectory() ? cacheBytes(child) : child.length();
        return bytes;
    }
    JSONObject upload(File file, String name) throws Exception {
        if (Thread.currentThread().isInterrupted()) throw new InterruptedIOException("Cancelado");
        HttpURLConnection c = connection("POST", "/api/v1/upload");
        activeTransfer = c;
        try {
            if (file.length() <= 0 || file.length() > MAX_FILE) throw new IOException("El archivo debe ocupar entre 1 byte y 512 MB.");
            c.setDoOutput(true); c.setReadTimeout(120000); c.setRequestProperty("Content-Type", "application/octet-stream");
            c.setRequestProperty("X-File-Name", URLEncoder.encode(name, "UTF-8").replace("+", "%20"));
            c.setRequestProperty("X-Content-SHA256", hash(file)); c.setFixedLengthStreamingMode(file.length());
            try (InputStream in = new FileInputStream(file); OutputStream out = c.getOutputStream()) {
                byte[] buffer = new byte[65536]; int count;
                while ((count = in.read(buffer)) != -1) {
                    if (Thread.currentThread().isInterrupted()) throw new InterruptedIOException("Envío cancelado");
                    out.write(buffer, 0, count);
                }
            }
            int status = c.getResponseCode();
            JSONObject value = new JSONObject(readText(status == 200 ? c.getInputStream() : c.getErrorStream(), 65536));
            if (status != 200) throw new IOException(value.optString("error", "No se completó el envío"));
            if (!hash(file).equals(value.optString("sha256"))) throw new IOException("No se pudo verificar el archivo recibido por el PC.");
            return value;
        } finally { c.disconnect(); if (activeTransfer == c) activeTransfer = null; }
    }
    void download(String id, File target) throws Exception {
        if (Thread.currentThread().isInterrupted()) throw new InterruptedIOException("Cancelado");
        HttpURLConnection c = connection("GET", "/api/v1/books/" + id + "/file");
        activeTransfer = c;
        File temporary = new File(target.getParentFile(), target.getName() + ".part");
        try {
            if (c.getResponseCode() != 200) throw new IOException("No se pudo descargar el libro. Actualiza sus detalles.");
            long expected = c.getContentLengthLong();
            if (expected <= 0 || expected > MAX_FILE) throw new IOException("Tamaño de libro no admitido.");
            File cache = target.getParentFile().getParentFile(); cache.mkdirs();
            if (cacheBytes(cache) + expected > 1024L * 1024 * 1024 || cache.getUsableSpace() < expected + 64L * 1024 * 1024)
                throw new IOException("Falta espacio para la copia. En Ajustes de Android → Aplicaciones → Mi biblioteca → Almacenamiento puedes borrar la caché; los originales del PC se conservan.");
            String signature = c.getHeaderField("X-Content-SHA256");
            if (signature == null || !signature.matches("[a-fA-F0-9]{64}")) throw new IOException("El PC no envió la firma del archivo.");
            target.getParentFile().mkdirs(); long total = 0;
            try (InputStream in = c.getInputStream(); FileOutputStream out = new FileOutputStream(temporary)) {
                byte[] buffer = new byte[65536]; int count;
                while ((count = in.read(buffer)) != -1) {
                    if (Thread.currentThread().isInterrupted()) throw new InterruptedIOException("Descarga cancelada");
                    total += count; if (total > expected) throw new IOException("El archivo cambió durante la descarga");
                    out.write(buffer, 0, count);
                }
                out.getFD().sync();
            }
            if (total != expected || !hash(temporary).equalsIgnoreCase(signature)) throw new IOException("La firma del libro no coincide. No se abrirá esta copia.");
            if (!temporary.renameTo(target)) throw new IOException("No se pudo guardar la copia verificada.");
        } finally { c.disconnect(); if (activeTransfer == c) activeTransfer = null; if (temporary.exists()) temporary.delete(); }
    }
}
