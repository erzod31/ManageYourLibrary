package com.erzod31.manageyourlibrary;

import android.app.*;
import android.content.*;
import android.content.pm.ActivityInfo;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.*;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;

/** Compiled only into the distinct QA package. No hooks or fixture CA in release. */
public final class QaInstrumentation extends Instrumentation {
    private Bundle arguments;
    private MainActivity activity;
    private final JSONArray checks = new JSONArray();
    private final JSONObject report = new JSONObject();
    interface Checked { void run() throws Exception; }
    @Override public void onCreate(Bundle args) { super.onCreate(args); arguments = args; start(); }
    private void check(String name, Checked test) throws Exception {
        long start = System.nanoTime(); test.run();
        checks.put(new JSONObject().put("name", name).put("passed", true).put("milliseconds", (System.nanoTime() - start) / 1000000));
    }
    private void require(boolean condition, String message) { if (!condition) throw new AssertionError(message); }
    private void ui(Runnable action) { runOnMainSync(action); waitForIdleSync(); }
    private View find(View root, String text) {
        if (root.getContentDescription() != null && text.contentEquals(root.getContentDescription())) return root;
        if (root instanceof TextView && text.contentEquals(((TextView)root).getText())) return root;
        if (root instanceof ViewGroup) for (int i = 0; i < ((ViewGroup)root).getChildCount(); i++) {
            View found = find(((ViewGroup)root).getChildAt(i), text); if (found != null) return found;
        }
        return null;
    }
    private View await(String text) throws Exception {
        long deadline = System.currentTimeMillis() + 20000;
        while (System.currentTimeMillis() < deadline) {
            AtomicReference<View> value = new AtomicReference<>();
            ui(() -> value.set(find(activity.getWindow().getDecorView(), text)));
            if (value.get() != null) return value.get();
            Thread.sleep(100);
        }
        throw new AssertionError("Missing UI: " + text);
    }
    private void click(String text) throws Exception {
        ui(() -> {
            ListView list = activity.findViewById(202);
            if (list != null && list.getAdapter() != null) for (int i = 0; i < list.getAdapter().getCount(); i++) {
                Object item = list.getAdapter().getItem(i);
                if (item instanceof JSONObject && text.equals(((JSONObject)item).optString("title"))) list.setSelection(i);
            }
        });
        View view = await(text);
        while (!view.isClickable() && view.getParent() instanceof View) view = (View)view.getParent();
        final View clickable = view; ui(clickable::performClick);
    }
    private void screenshot(String name) throws Exception {
        Thread.sleep(500);
        Bitmap bitmap = getUiAutomation().takeScreenshot(); require(bitmap != null, "Screenshot unavailable");
        try (FileOutputStream stream = new FileOutputStream(new File(getTargetContext().getFilesDir(), name + ".png"))) { bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream); }
        bitmap.recycle();
    }
    private JSONObject job(DesktopApi api, String path, JSONObject body) throws Exception {
        String id = api.request("POST", path, body).getString("job_id");
        long deadline = System.currentTimeMillis() + 30000;
        while (System.currentTimeMillis() < deadline) {
            JSONObject result = api.request("GET", "/api/v1/jobs/" + id, null);
            String state = result.getString("state");
            if ("completed".equals(state)) return result.getJSONObject("result");
            require("queued".equals(state) || "running".equals(state), result.toString()); Thread.sleep(100);
        }
        throw new AssertionError("Desktop job timeout");
    }
    @Override public void onStart() {
        super.onStart();
        if ("updates".equals(arguments.getString("mode"))) {
            MainActivity initial=(MainActivity)startActivitySync(new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            UpdateQa.run(this,initial);return;
        }
        try {
            String address = arguments.getString("url"), code = arguments.getString("code");
            activity = (MainActivity)startActivitySync(new Intent(getTargetContext(), MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            if (arguments.getString("mode", "").startsWith("permission")) {
                check("android_17_runtime_network_permission_" + arguments.getString("mode"), () -> {
                    await("Vincular con el PC");
                    ui(() -> { ((EditText)activity.findViewById(101)).setText(address); ((EditText)activity.findViewById(102)).setText(code); activity.findViewById(103).performClick(); });
                    boolean deny = "permission-deny".equals(arguments.getString("mode"));
                    long deadline = System.currentTimeMillis() + 8000; boolean clicked = false;
                    while (System.currentTimeMillis() < deadline && !clicked) {
                        android.view.accessibility.AccessibilityNodeInfo node = getUiAutomation().getRootInActiveWindow();
                        if (node != null && node.getPackageName() != null) {
                            String id = node.getPackageName() + ":id/" + (deny ? "permission_deny_button" : "permission_allow_button");
                            java.util.List<android.view.accessibility.AccessibilityNodeInfo> buttons = node.findAccessibilityNodeInfosByViewId(id);
                            if (buttons.isEmpty()) buttons = node.findAccessibilityNodeInfosByViewId("com.android.permissioncontroller:id/" + (deny ? "permission_deny_button" : "permission_allow_button"));
                            if (!buttons.isEmpty()) clicked = buttons.get(0).performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK);
                        }
                        Thread.sleep(100);
                    }
                    require(clicked, "Runtime local-network permission dialog unavailable");
                    if (deny) await("Permite el acceso a la red local para conectar con tu PC. Puedes cambiarlo en los ajustes de Android.");
                    else await("Cosas que dejamos atrás");
                    screenshot(deny ? "network-permission-denied" : "network-permission-allowed");
                });
                report.put("passed", true); return;
            }
            if ("layout".equals(arguments.getString("mode"))) {
                check("large_font_navigation_and_scroll_layout", () -> {
                    click("Biblioteca"); await("Cosas que dejamos atrás"); screenshot("large-font-library");
                    for (String label : new String[]{"Biblioteca", "Favoritos", "Importar", "Actividad", "Conexión"}) {
                        View tab = await(label); android.graphics.Rect rect = new android.graphics.Rect();
                        ui(() -> { require(tab.getGlobalVisibleRect(rect), "Hidden navigation: " + label); });
                        require(rect.height() > 0 && rect.width() > 0, "Missing navigation bounds");
                    }
                    click("Conexión"); await("Apariencia"); screenshot("large-font-connection");
                    click("Importar"); await("Elegir libro del teléfono"); screenshot("large-font-import");
                    click("Actividad"); await("Planes pendientes"); screenshot("large-font-activity");
                });
                report.put("passed", true); return;
            }
            check("native_launch_and_pairing_ui", () -> {
                await("Vincular con el PC"); screenshot("first-use-light");
                ui(() -> { ((EditText)activity.findViewById(101)).setText(address); ((EditText)activity.findViewById(102)).setText(code); activity.findViewById(103).performClick(); });
                await("Cosas que dejamos atrás"); screenshot("library-light");
            });
            SecretStore store = new SecretStore(getTargetContext());
            DesktopApi api = new DesktopApi(store.url(), store.token(), true);
            check("encrypted_credential_and_https_address_validation", () -> {
                String saved = getTargetContext().getSharedPreferences("connection", 0).getString("credential", "");
                require(!saved.contains(store.token()) && saved.contains(":"), "Credential must be encrypted");
                for (String bad : new String[]{"http://pc.example.ts.net", "https://example.com", "https://pc.example.ts.net/evil", "https://user@pc.example.ts.net", "https://10.0.2.2:18443"}) {
                    boolean refused = false; try { DesktopApi.validateAddress(bad, false); } catch (Exception expected) { refused = true; }
                    require(refused, "Unsafe production address accepted: " + bad);
                }
            });
            check("search_debounce_latest_result_and_reset", () -> {
                ui(() -> { EditText search = activity.findViewById(201); search.setText("nunca coincide"); search.setText("Mapas"); });
                await("1–1 / 1"); await("Mapas del silencio");
                ui(() -> ((EditText)activity.findViewById(201)).setText("")); await("1–6 / 6");
            });
            JSONObject first = api.request("GET", "/api/v1/books", null).getJSONArray("books").getJSONObject(0);
            check("real_desktop_favorite_and_metadata_roundtrip", () -> {
                job(api, "/api/v1/books/" + first.getString("id") + "/metadata", new JSONObject().put("revision", first.getString("revision")).put("favorite", true));
                JSONObject updated = api.request("GET", "/api/v1/books/" + first.getString("id"), null);
                require(updated.getBoolean("favorite"), "Favorite did not persist");
                require(!first.getString("revision").equals(updated.getString("revision")), "Revision did not change");
            });
            check("verified_download_and_read_only_provider", () -> {
                File target = new File(new File(new File(getTargetContext().getCacheDir(), "books"), "00112233445566778899aabbccddeeff"), "phone-original.epub");
                api.download(first.getString("id"), target);
                Uri uri = new Uri.Builder().scheme("content").authority(getTargetContext().getPackageName() + ".files").appendPath(target.getParentFile().getName()).appendPath(target.getName()).build();
                try (InputStream in = getTargetContext().getContentResolver().openInputStream(uri)) { require(in != null && in.read() == 'P', "EPUB ZIP not readable"); }
                boolean refused = false; try { getTargetContext().getContentResolver().openOutputStream(uri); } catch (Exception expected) { refused = true; }
                require(refused, "Provider allowed a write");
                String hash = DesktopApi.hash(target);
                JSONObject upload = api.upload(target, "phone-original.epub");
                require(hash.equals(upload.getString("sha256")), "Upload integrity mismatch");
                JSONObject preview = job(api, "/api/v1/uploads/" + upload.getString("upload_id") + "/import-preview",
                    new JSONObject().put("confirmed", true).put("title", "Libro desde Android QA").put("author", "Autora de prueba"));
                require(preview.getBoolean("preview_only"), "Import was not previewed");
                JSONObject applied = job(api, "/api/v1/plans/" + preview.getString("plan_id"), new JSONObject().put("confirmed", true));
                require(api.request("GET", "/api/v1/books", null).getInt("total") == 7, "Import did not update catalog");
                job(api, "/api/v1/undo", new JSONObject().put("confirmed", true).put("batch", applied.getString("undo_batch")));
                require(api.request("GET", "/api/v1/books", null).getInt("total") == 6, "Undo did not restore catalog");
                require(hash.equals(DesktopApi.hash(target)), "Phone original changed");
            });
            check("recoverable_quarantine_from_android_protocol", () -> {
                JSONObject book = api.request("GET", "/api/v1/books/" + first.getString("id"), null);
                JSONObject preview = job(api, "/api/v1/books/" + book.getString("id") + "/quarantine-preview", new JSONObject().put("revision", book.getString("revision")));
                JSONObject applied = job(api, "/api/v1/plans/" + preview.getString("plan_id"), new JSONObject().put("confirmed", true));
                require(api.request("GET", "/api/v1/books", null).getInt("total") == 5, "Quarantine missing");
                job(api, "/api/v1/undo", new JSONObject().put("confirmed", true).put("batch", applied.getString("undo_batch")));
                require(api.request("GET", "/api/v1/books", null).getInt("total") == 6, "Quarantine undo missing");
            });
            check("selected_file_upload_ui_keeps_phone_original", () -> {
                File original = new File(new File(new File(getTargetContext().getCacheDir(), "books"), "00112233445566778899aabbccddeeff"), "phone-original.epub");
                String hash = DesktopApi.hash(original); int before = api.request("GET", "/api/v1/uploads", null).getJSONArray("uploads").length();
                Uri uri = new Uri.Builder().scheme("content").authority(getTargetContext().getPackageName() + ".files").appendPath(original.getParentFile().getName()).appendPath(original.getName()).build();
                ui(() -> activity.onActivityResult(200, Activity.RESULT_OK, new Intent().setData(uri)));
                long deadline = System.currentTimeMillis() + 15000; boolean received = false;
                while (System.currentTimeMillis() < deadline) { if (api.request("GET", "/api/v1/uploads", null).getJSONArray("uploads").length() > before) { received = true; break; } Thread.sleep(100); }
                require(received, "Selected file did not reach desktop inbox");
                await("Revisar metadatos manualmente"); screenshot("received-upload");
                require(hash.equals(DesktopApi.hash(original)), "Selected phone original was modified");
                click("Biblioteca"); await("Cosas que dejamos atrás");
            });
            check("details_and_global_dark_theme_navigation", () -> {
                click("Mapas del silencio"); await("Ruta completa en el PC\n" + api.request("GET", "/api/v1/books?q=Mapas", null).getJSONArray("books").getJSONObject(0).getString("path"));
                screenshot("details-light"); click("Conexión"); click("Oscuro"); screenshot("connection-dark");
                click("Biblioteca"); await("Cosas que dejamos atrás"); screenshot("library-dark");
                click("Importar"); await("Bandeja del PC"); screenshot("import-dark");
                click("Actividad"); await("Planes pendientes"); screenshot("activity-dark");
            });
            check("rotation_recreation_and_keystore_reconnect", () -> {
                ActivityMonitor monitor = addMonitor(MainActivity.class.getName(), null, false);
                ui(() -> activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE));
                Activity rotated = monitor.waitForActivityWithTimeout(8000); require(rotated instanceof MainActivity, "Rotation did not recreate activity"); activity = (MainActivity)rotated;
                await("Planes pendientes"); screenshot("activity-landscape-dark"); removeMonitor(monitor);
            });
            report.put("passed", true);
        } catch (Throwable failure) {
            try { report.put("passed", false).put("failure", failure.toString()); StringWriter trace = new StringWriter(); failure.printStackTrace(new PrintWriter(trace)); report.put("trace", trace.toString()); } catch (Exception ignored) { }
        } finally {
            try {
                report.put("checks", checks).put("api", Build.VERSION.SDK_INT).put("android", Build.VERSION.RELEASE).put("device", Build.MODEL);
                try (FileOutputStream out = new FileOutputStream(new File(getTargetContext().getFilesDir(), "qa-report.json"))) { out.write(report.toString(2).getBytes("UTF-8")); }
                Bundle result = new Bundle(); result.putString("report", report.toString()); finish(report.optBoolean("passed") ? Activity.RESULT_OK : Activity.RESULT_CANCELED, result);
            } catch (Exception failure) { finish(Activity.RESULT_CANCELED, new Bundle()); }
        }
    }
}
