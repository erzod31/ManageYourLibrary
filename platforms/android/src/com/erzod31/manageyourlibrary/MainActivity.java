package com.erzod31.manageyourlibrary;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.database.Cursor;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.*;
import android.provider.OpenableColumns;
import android.text.*;
import android.text.method.PasswordTransformationMethod;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.*;

public final class MainActivity extends Activity {
    interface Work<T> { T run() throws Exception; }
    interface Done<T> { void accept(T value) throws Exception; }
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService network = new ThreadPoolExecutor(3, 3, 0L, TimeUnit.SECONDS, new ArrayBlockingQueue<Runnable>(32));
    private final ExecutorService coverNetwork = new ThreadPoolExecutor(2, 2, 0L, TimeUnit.SECONDS, new ArrayBlockingQueue<Runnable>(24));
    private final ArrayList<JSONObject> books = new ArrayList<>();
    private final ArrayList<JSONObject> jobs = new ArrayList<>();
    private final android.util.LruCache<String, Bitmap> covers = new android.util.LruCache<String, Bitmap>(12 * 1024 * 1024) {
        @Override protected int sizeOf(String key, Bitmap value) { return value.getAllocationByteCount(); }
    };
    private final Set<String> loadingCovers = Collections.synchronizedSet(new HashSet<String>());
    private SecretStore secrets;
    private DesktopApi api;
    private LinearLayout root, body, footer, header;
    private TextView status, heading, pageLabel;
    private EditText search, serverInput, codeInput;
    private BookAdapter bookAdapter;
    private JobAdapter jobAdapter;
    private Button next, previous;
    private JSONObject selected;
    private String screen = "library", scope = "library", query = "", format = "all";
    private int offset = 0, total = 0, generation = 0, searchEpoch = 0;
    private boolean destroyed = false, resumed = false;
    private boolean jobsLoading = false;
    private int background, surface, ink, muted, border, accent;
    private Future<?> transfer;
    private AppUpdates appUpdates;
    private JSONObject updateOffer;
    private File verifiedUpdate;
    private boolean updateBusy = false;
    private TextView updateStatus;
    private Button checkUpdateButton, downloadUpdateButton, installUpdateButton;
    private boolean transferring = false;
    private int transferEpoch = 0;
    private Button cancelTransfer;
    private final Runnable searchRefresh = () -> { offset = 0; loadBooks(); };
    private final Runnable activityRefresh = new Runnable() {
        @Override public void run() {
            if (resumed && "activity".equals(screen) && api != null) { loadJobs(false); handler.postDelayed(this, 1800); }
        }
    };

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        secrets = new SecretStore(this);
        appUpdates = new AppUpdates(this);
        if (state != null) {
            screen = state.getString("screen", "library"); scope = state.getString("scope", "library");
            query = state.getString("query", ""); format = state.getString("format", "all");
            offset = state.getInt("offset", 0);
        }
        try { if (!secrets.token().isEmpty()) api = new DesktopApi(secrets.url(), secrets.token(), testing()); }
        catch (Exception ex) { api = null; }
        if (api == null) screen = "settings";
        applyColors(); buildRoot(); showScreen(screen);
        if (Build.VERSION.SDK_INT >= 33) getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
            android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::back);
    }
    @Override protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        state.putString("screen", "details".equals(screen) ? "library" : screen); state.putString("scope", scope);
        state.putString("query", query); state.putString("format", format); state.putInt("offset", offset);
    }
    @Override protected void onResume() {
        super.onResume(); resumed = true;
        if ("activity".equals(screen)) { handler.removeCallbacks(activityRefresh); handler.post(activityRefresh); }
    }
    @Override protected void onPause() { resumed = false; handler.removeCallbacks(activityRefresh); super.onPause(); }
    @Override protected void onDestroy() {
        destroyed = true; if (transfer != null) transfer.cancel(true); if (api != null) api.cancelTransfers();
        appUpdates.cancel();
        handler.removeCallbacksAndMessages(null); network.shutdownNow(); coverNetwork.shutdownNow(); covers.evictAll(); super.onDestroy();
    }
    @Override public void onBackPressed() { back(); }
    private void back() {
        if (!"library".equals(screen) && api != null) { showScreen("library"); return; }
        finish();
    }
    private AlertDialog.Builder dialog() {
        boolean dark = Color.red(ink) > 180;
        return new AlertDialog.Builder(new android.view.ContextThemeWrapper(this, dark ? R.style.AppDialogDark : R.style.AppDialogLight));
    }
    private boolean testing() { return (getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0; }
    private int dp(float value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private void applyColors() {
        String preference = getPreferences(MODE_PRIVATE).getString("theme", "system");
        boolean dark = "dark".equals(preference) || ("system".equals(preference) &&
            (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES);
        background = Color.parseColor(dark ? "#191B1E" : "#F7F3ED");
        surface = Color.parseColor(dark ? "#24272B" : "#FFFDFA"); ink = Color.parseColor(dark ? "#F4EEE5" : "#262422");
        muted = Color.parseColor(dark ? "#BCC0C6" : "#656970"); border = Color.parseColor(dark ? "#42464D" : "#DED8D0");
        accent = Color.parseColor(dark ? "#DC9D7E" : "#A15840");
        getWindow().setStatusBarColor(background); getWindow().setNavigationBarColor(surface);
        getWindow().getDecorView().setSystemUiVisibility(dark ? 0 : View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        applySystemBars();
    }
    private void applySystemBars() {
        if (Build.VERSION.SDK_INT >= 30 && getWindow().getInsetsController() != null) {
            int mask = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
            getWindow().getInsetsController().setSystemBarsAppearance(Color.red(ink) > 180 ? 0 : mask, mask);
        }
    }
    private GradientDrawable shape(int color, int stroke, int radius) {
        GradientDrawable d = new GradientDrawable(); d.setColor(color); d.setCornerRadius(dp(radius)); d.setStroke(dp(1), stroke); return d;
    }
    private LinearLayout column() { LinearLayout view = new LinearLayout(this); view.setOrientation(LinearLayout.VERTICAL); return view; }
    private LinearLayout row() { LinearLayout view = new LinearLayout(this); view.setOrientation(LinearLayout.HORIZONTAL); view.setGravity(Gravity.CENTER_VERTICAL); return view; }
    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        view.setTypeface(null, bold ? Typeface.BOLD : Typeface.NORMAL); view.setPadding(0, dp(3), 0, dp(3)); return view;
    }
    private Button button(String label, boolean primary, Runnable command) {
        Button view = new Button(this); view.setText(label); view.setAllCaps(false); view.setTextSize(15);
        view.setMinHeight(dp(48)); view.setMinimumWidth(0); view.setMinWidth(0); view.setPadding(dp(14), dp(9), dp(14), dp(9));
        view.setTextColor(new android.content.res.ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled}, new int[]{}}, new int[]{muted, primary ? background : ink}));
        android.graphics.drawable.StateListDrawable backgrounds = new android.graphics.drawable.StateListDrawable();
        backgrounds.addState(new int[]{-android.R.attr.state_enabled}, shape(background, border, 13));
        backgrounds.addState(new int[]{}, new android.graphics.drawable.RippleDrawable(android.content.res.ColorStateList.valueOf((accent & 0x00FFFFFF) | 0x33000000), shape(primary ? accent : surface, primary ? accent : border, 13), null));
        view.setBackground(backgrounds); view.setStateListAnimator(null);
        view.setOnClickListener(v -> command.run()); return view;
    }
    private EditText field(String hint, String value) {
        EditText view = new EditText(this); view.setText(value); view.setHint(hint); view.setTextSize(16);
        view.setTextColor(ink); view.setHintTextColor(muted); view.setSingleLine(true); view.setMinHeight(dp(54));
        view.setPadding(dp(14), dp(10), dp(14), dp(10)); view.setBackground(shape(surface, border, 13));
        view.setFilters(new InputFilter[]{new InputFilter.LengthFilter(240)}); return view;
    }
    private void spaced(LinearLayout parent, View view, int top) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2); p.topMargin = dp(top); parent.addView(view, p);
    }
    private LinearLayout card(LinearLayout parent) {
        LinearLayout box = column(); box.setPadding(dp(16), dp(12), dp(16), dp(16)); box.setBackground(shape(surface, border, 17));
        spaced(parent, box, 12); return box;
    }
    private LinearLayout scrollBody() {
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true);
        LinearLayout container = column(); container.setPadding(dp(16), 0, dp(16), dp(20));
        scroll.addView(container); body.addView(scroll, new LinearLayout.LayoutParams(-1, -1)); return container;
    }
    private void buildRoot() {
        root = column(); root.setBackgroundColor(background); setContentView(root);
        root.post(this::applySystemBars);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                android.graphics.Insets keyboard = insets.getInsets(WindowInsets.Type.ime());
                view.setPadding(bars.left, bars.top, bars.right, Math.max(bars.bottom, keyboard.bottom));
            } else view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets;
        });
        header = row(); header.setPadding(dp(16), dp(10), dp(12), dp(4));
        Icon icon = new Icon("book", accent); icon.setContentDescription("Mi biblioteca"); header.addView(icon, new LinearLayout.LayoutParams(dp(32), dp(36)));
        heading = text("Mi biblioteca", 24, ink, false); heading.setTypeface(Typeface.create("serif", Typeface.NORMAL));
        LinearLayout.LayoutParams h = new LinearLayout.LayoutParams(0, -2, 1); h.leftMargin = dp(10); header.addView(heading, h);
        Icon refresh = new Icon("refresh", accent); refresh.setContentDescription("Actualizar pantalla"); refresh.setFocusable(true);
        refresh.setOnClickListener(v -> showScreen(screen)); header.addView(refresh, new LinearLayout.LayoutParams(dp(48), dp(48)));
        root.addView(header);
        status = text("Biblioteca del PC · conexión privada", 12, muted, false); status.setPadding(dp(16), dp(2), dp(16), dp(8)); root.addView(status);
        status.setMaxLines(3); status.setEllipsize(TextUtils.TruncateAt.END);
        cancelTransfer = button("Cancelar transferencia", false, () -> {
            transferEpoch++;
            if (transfer != null) transfer.cancel(true); if (api != null) api.cancelTransfers();
            transferring = false; cancelTransfer.setVisibility(View.GONE); status.setText("Transferencia cancelada · originales conservados");
        });
        cancelTransfer.setVisibility(transferring ? View.VISIBLE : View.GONE); root.addView(cancelTransfer);
        body = column(); root.addView(body, new LinearLayout.LayoutParams(-1, 0, 1));
        footer = row(); footer.setPadding(dp(4), dp(6), dp(4), dp(6)); footer.setBackgroundColor(surface); root.addView(footer);
        String[][] navigation = {{"book", "Biblioteca", "library"}, {"heart", "Favoritos", "favorites"},
            {"upload", "Importar", "import"}, {"history", "Actividad", "activity"}, {"settings", "Conexión", "settings"}};
        for (String[] item : navigation) {
            LinearLayout tab = column(); tab.setGravity(Gravity.CENTER); tab.setMinimumHeight(dp(60));
            Icon pic = new Icon(item[0], accent); tab.addView(pic, new LinearLayout.LayoutParams(dp(26), dp(26)));
            TextView label = text(item[1], 11, ink, false); label.setGravity(Gravity.CENTER); label.setMaxLines(2); tab.addView(label);
            tab.setContentDescription(item[1]); tab.setFocusable(true); tab.setClickable(true);
            pic.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO); label.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
            tab.setOnClickListener(v -> {
                if ("favorites".equals(item[2])) { scope = "favorites"; offset = 0; showScreen("library"); }
                else { if ("library".equals(item[2])) { scope = "library"; offset = 0; } showScreen(item[2]); }
            });
            footer.addView(tab, new LinearLayout.LayoutParams(0, -2, 1));
        }
    }
    private <T> Future<?> work(Work<T> operation, Done<T> done) {
        try {
            return network.submit(() -> {
                try {
                    T result = operation.run();
                    handler.post(() -> { if (!destroyed) try { done.accept(result); } catch (Exception ex) { error(ex); } });
                } catch (Exception ex) { handler.post(() -> { if (!destroyed) error(ex); }); }
            });
        } catch (RejectedExecutionException ignored) { if (!destroyed) status.setText("Espera a que terminen las solicitudes pendientes."); return null; }
    }
    private void error(Exception ex) {
        String message = ex.getMessage();
        if (ex instanceof UnknownHostException || ex instanceof ConnectException || ex instanceof SocketTimeoutException)
            message = "No se encuentra el PC. Conecta Tailscale en ambos dispositivos y activa Android / Tailscale en el escritorio.";
        if (ex instanceof javax.net.ssl.SSLException) message = "No se pudo verificar HTTPS. Copia la dirección de Tailscale del PC y comprueba fecha y hora del móvil.";
        if (message == null || message.isEmpty()) message = "No se pudo completar la operación. Revisa la conexión y vuelve a intentarlo.";
        status.setText(message); Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }
    private void showScreen(String target) {
        generation++; handler.removeCallbacks(searchRefresh); handler.removeCallbacks(activityRefresh); body.removeAllViews();
        screen = api == null && !"settings".equals(target) ? "settings" : target;
        if ("library".equals(screen)) library();
        else if ("details".equals(screen) && selected != null) details(selected);
        else if ("import".equals(screen)) imports();
        else if ("activity".equals(screen)) activity();
        else settings();
    }
    private void settings() {
        heading.setText("Conexión"); LinearLayout content = scrollBody();
        LinearLayout intro = card(content); intro.addView(text("Tu biblioteca, contigo", 23, ink, true));
        intro.addView(text("El teléfono se conecta al PC por Tailscale. El catálogo y el OCR Indra permanecen en el escritorio.", 15, muted, false));
        LinearLayout connection = card(content); connection.addView(text(api == null ? "Vincular con el PC" : "PC vinculado", 18, ink, true));
        serverInput = field("https://tu-pc.tu-red.ts.net:10443", secrets.url()); serverInput.setId(101);
        serverInput.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI); spaced(connection, serverInput, 10);
        codeInput = field("Código de 8 dígitos del PC", ""); codeInput.setId(102); codeInput.setSaveEnabled(false);
        codeInput.setInputType(android.text.InputType.TYPE_CLASS_NUMBER | android.text.InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        codeInput.setTransformationMethod(PasswordTransformationMethod.getInstance()); codeInput.setFilters(new InputFilter[]{new InputFilter.LengthFilter(8)});
        spaced(connection, codeInput, 10); Button pair = button("Vincular de forma privada", true, this::pair); pair.setId(103); spaced(connection, pair, 12);
        spaced(connection, button("Abrir Tailscale", false, () -> {
            Intent launch = getPackageManager().getLaunchIntentForPackage("com.tailscale.ipn");
            if (launch != null) startActivity(launch); else dialog().setTitle("Tailscale").setMessage("Instala la aplicación oficial Tailscale y conecta el móvil a la misma red que el PC.").setPositiveButton("Entendido", null).show();
        }), 10);
        if (api != null) spaced(connection, button("Desvincular este móvil", false, () -> dialog()
            .setTitle("Desvincular").setMessage("Se revocará el acceso de este móvil en el PC y se eliminará su credencial local. La biblioteca se conserva.")
            .setPositiveButton("Desvincular", (d, w) -> {
                DesktopApi client = api;
                work(() -> client.request("POST", "/api/v1/unpair", new JSONObject()), value -> { client.cancelTransfers(); api = null; secrets.clear(); covers.evictAll(); showScreen("settings"); });
            })
            .setNegativeButton("Cancelar", null).show()), 10);
        LinearLayout appearance = card(content); appearance.addView(text("Apariencia", 18, ink, true));
        LinearLayout themes = row(); String[] names = {"Sistema", "Claro", "Oscuro"}, keys = {"system", "light", "dark"};
        for (int i = 0; i < names.length; i++) {
            final String value = keys[i]; Button b = button(names[i], false, () -> { getPreferences(MODE_PRIVATE).edit().putString("theme", value).apply(); applyColors(); buildRoot(); showScreen(screen); });
            LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(0, -2, 1); p.setMargins(dp(2), dp(8), dp(2), 0); themes.addView(b, p);
        }
        appearance.addView(themes);
        LinearLayout help = card(content); help.addView(text("Primer uso", 18, ink, true));
        help.addView(text("1. Abre la nueva edición de escritorio.\n2. Configuración → Android / Tailscale → Activar acceso.\n3. Copia su dirección HTTPS y genera un código.\n4. Con Tailscale conectado en el móvil, vincula aquí.", 15, muted, false));
        spaced(help, button("Licencias y condiciones de Indra OCR", false, () -> {
            work(() -> DesktopApi.readText(getAssets().open("licenses/PROJECT_LICENSE.txt"), 65536) + "\n\n" +
                DesktopApi.readText(getAssets().open("licenses/NOTICE.txt"), 65536) + "\n\n" +
                DesktopApi.readText(getAssets().open("licenses/MODEL_LICENSE.txt"), 65536), value -> {
                TextView license = text(value, 13, ink, false); license.setTextIsSelectable(true); license.setPadding(dp(16), dp(12), dp(16), dp(16));
                ScrollView scroll = new ScrollView(this); scroll.addView(license);
                dialog().setTitle("Indra OCR · Datalab").setView(scroll).setPositiveButton("Cerrar", null).show();
            });
        }), 12);
        help.addView(text("Sin anuncios, analítica ni envío de libros a servicios OCR externos. El PC debe permanecer encendido y el acceso móvil activo.", 13, muted, false));
        updateCard(content);
    }
    private void updateCard(LinearLayout content) {
        LinearLayout card=card(content);card.addView(text("Actualizar esta aplicación",19,ink,true));
        String current="";try{current=appUpdates.installed().versionName;}catch(Exception ignored){}
        card.addView(text("Versión actual: "+current+" · APK firmado del PC vinculado",14,muted,false));
        updateStatus=text(api==null?"Vincula el PC para buscar actualizaciones de esta app.":"No se busca ni descarga nada automáticamente.",14,muted,false);updateStatus.setId(801);card.addView(updateStatus);
        checkUpdateButton=button("Buscar actualización de la app",false,this::checkAppUpdate);checkUpdateButton.setId(802);spaced(card,checkUpdateButton,8);
        downloadUpdateButton=button("Descargar y verificar APK",false,this::downloadAppUpdate);downloadUpdateButton.setId(803);spaced(card,downloadUpdateButton,8);
        installUpdateButton=button("Instalar actualización",true,this::installAppUpdate);installUpdateButton.setId(804);spaced(card,installUpdateButton,8);
        spaced(card,button("Cancelar actualización",false,()->{appUpdates.cancel();updateStatus.setText("Cancelada · versión instalada conservada");}),8);
        try {
            JSONObject pending=appUpdates.pending();
            if(pending!=null){JSONObject metadata=pending.getJSONObject("metadata");
                if(AppUpdates.compare(metadata.getString("version"),appUpdates.installed().versionName)>0){
                    File candidate=new File(appUpdates.directory,pending.getString("file"));
                    if(candidate.isFile()){updateOffer=metadata;verifiedUpdate=candidate;updateStatus.setText("APK preparado: "+metadata.optString("version")+". Se verificará otra vez antes de instalar.");}
                }else updateStatus.setText("Actualización completada · versión actual "+appUpdates.installed().versionName);
            }
        }catch(Exception ex){updateStatus.setText("No se pudo recuperar el paquete pendiente. Busca de nuevo; la versión instalada se conserva.");}
        updateButtons();
        card.addView(text("Android pedirá autorización para instalar desde esta app y confirmará la sustitución. Conserva la firma y los datos. Al finalizar, usa Abrir en el sistema o vuelve a abrir Mi biblioteca.",13,muted,false));
    }
    private void updateButtons(){
        if(checkUpdateButton!=null){checkUpdateButton.setEnabled(api!=null&&!updateBusy);downloadUpdateButton.setEnabled(updateOffer!=null&&verifiedUpdate==null&&!updateBusy);installUpdateButton.setEnabled(verifiedUpdate!=null&&!updateBusy);}
    }
    private void updateWork(Work<?> operation,Runnable done){
        updateBusy=true;updateButtons();
        Future<?> request=work(()->{
            try{return operation.run();}
            finally{handler.post(()->{updateBusy=false;if(!destroyed)updateButtons();});}
        },result->{done.run();});
        if(request==null){updateBusy=false;updateButtons();}
    }
    private void checkAppUpdate(){
        if(api==null||updateBusy)return;DesktopApi client=api;appUpdates.cancelled.set(false);
        updateStatus.setText("Consultando el paquete firmado del PC…");
        final JSONObject[] result=new JSONObject[1];
        updateWork(()->{result[0]=appUpdates.check(client);return null;},()->{
            if(!result[0].optBoolean("available")){updateOffer=null;verifiedUpdate=null;updateStatus.setText("No hay una versión más reciente. Paquete del PC: "+result[0].optString("version"));}
            else{updateOffer=result[0];verifiedUpdate=null;updateStatus.setText("Disponible: "+updateOffer.optString("version")+" · "+updateOffer.optLong("bytes")/1024+" KiB. El certificado coincide con esta app.");}
            updateButtons();
        });
    }
    private void downloadAppUpdate(){
        if(api==null||updateOffer==null||updateBusy)return;DesktopApi client=api;JSONObject metadata=updateOffer;
        appUpdates.cancelled.set(false);updateStatus.setText("Descargando APK y verificando versión, tamaño, SHA-256 y certificado…");
        final File[] result=new File[1];
        updateWork(()->{result[0]=appUpdates.download(client,metadata);return null;},()->{verifiedUpdate=result[0];updateStatus.setText("APK verificado. Pulsa Instalar para autorizar el cambio en Android.");updateButtons();});
    }
    private void installAppUpdate(){
        if(verifiedUpdate==null||updateOffer==null||updateBusy)return;
        dialog().setTitle("Confirmar actualización").setMessage("¿Actualizar Mi biblioteca a "+updateOffer.optString("version")+"? Se conserva la conexión y los datos. Android mostrará sus propias confirmaciones y permitirá abrir la nueva versión.")
            .setNegativeButton("Cancelar",null).setPositiveButton("Continuar",(dialog,which)->{
                appUpdates.cancelled.set(false);File file=verifiedUpdate;JSONObject metadata=updateOffer;
                updateWork(()->{
                    appUpdates.verify(file,metadata);return null;
                },()->{
                    try{appUpdates.handoff(file,metadata,true,getPackageManager().canRequestPackageInstalls(),(intent,request)->startActivityForResult(intent,request));}
                    catch(Exception ex){error(ex);}
                });
            }).show();
    }
    private void pair() {
        try { DesktopApi.validateAddress(serverInput.getText().toString(), testing()); }
        catch (Exception ex) { error(ex); return; }
        if (Build.VERSION.SDK_INT >= 37 && checkSelfPermission("android.permission.ACCESS_LOCAL_NETWORK") != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{"android.permission.ACCESS_LOCAL_NETWORK"}, 100); return;
        }
        String address = serverInput.getText().toString(), code = codeInput.getText().toString();
        if (!code.matches("[0-9]{8}")) { error(new Exception("Escribe el código de 8 dígitos que muestra el PC.")); return; }
        status.setText("Vinculando con tu PC…");
        work(() -> {
            DesktopApi client = new DesktopApi(address, "", testing());
            JSONObject hello = client.request("GET", "/api/v1/health", null);
            if (hello.optInt("protocol") != 1) throw new IOException("Actualiza la aplicación de escritorio antes de vincular.");
            return client.request("POST", "/api/v1/pair", new JSONObject().put("code", code).put("device", Build.MANUFACTURER + " " + Build.MODEL));
        }, value -> {
            String base = DesktopApi.validateAddress(address, testing()); secrets.save(base, value.getString("token"));
            api = new DesktopApi(base, value.getString("token"), testing()); codeInput.setText("");
            status.setText("Vinculado de forma privada"); showScreen("library");
        });
    }
    @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results);
        if (request == 100 && results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) pair();
        else if (request == 100) error(new Exception("Permite el acceso a la red local para conectar con tu PC. Puedes cambiarlo en los ajustes de Android."));
    }
    private void library() {
        heading.setText("favorites".equals(scope) ? "Favoritos" : "Mi biblioteca");
        LinearLayout controls = column(); controls.setPadding(dp(16), dp(4), dp(16), dp(8)); body.addView(controls);
        search = field("Buscar título, autor, etiqueta…", query); search.setId(201); search.setImeOptions(android.view.inputmethod.EditorInfo.IME_ACTION_SEARCH); controls.addView(search);
        search.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int a, int c, int f) { }
            public void onTextChanged(CharSequence s, int a, int before, int count) { query = s.toString(); handler.removeCallbacks(searchRefresh); handler.postDelayed(searchRefresh, 280); }
            public void afterTextChanged(Editable e) { }
        });
        HorizontalScrollView filters = new HorizontalScrollView(this); filters.setHorizontalScrollBarEnabled(false); LinearLayout chips = row(); filters.addView(chips); spaced(controls, filters, 8);
        String[][] values = {{"Todos", "all"}, {"EPUB", "epub"}, {"PDF", "pdf"}, {"CBZ", "cbz"}, {"Series", "@series"}, {"Etiquetas", "@tags"}};
        for (String[] item : values) {
            Button b = button(item[0], item[1].equals(format) || item[1].equals("@" + scope), () -> {
                if (item[1].startsWith("@")) scope = item[1].substring(1); else { format = item[1]; if (!"favorites".equals(scope)) scope = "library"; }
                offset = 0; showScreen("library");
            }); LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-2, -2); p.rightMargin = dp(7); chips.addView(b, p);
        }
        ListView list = new ListView(this); list.setId(202); list.setDivider(null); list.setClipToPadding(false); list.setPadding(dp(12), 0, dp(12), dp(8));
        bookAdapter = new BookAdapter(); list.setAdapter(bookAdapter); list.setOnItemClickListener((parent, view, position, id) -> openDetails(books.get(position).optString("id")));
        body.addView(list, new LinearLayout.LayoutParams(-1, 0, 1));
        LinearLayout pages = row(); pages.setPadding(dp(16), dp(4), dp(16), dp(8));
        previous = button("Anterior", false, () -> { offset = Math.max(0, offset - 30); loadBooks(); }); pages.addView(previous);
        pageLabel = text("…", 12, muted, false); pageLabel.setGravity(Gravity.CENTER); pages.addView(pageLabel, new LinearLayout.LayoutParams(0, -2, 1));
        next = button("Siguiente", false, () -> { offset += 30; loadBooks(); }); pages.addView(next); body.addView(pages);
        loadBooks();
    }
    private void loadBooks() {
        if (api == null || !"library".equals(screen)) return;
        int current = generation, epoch = ++searchEpoch; DesktopApi client = api;
        String path = "/api/v1/books?offset=" + offset + "&limit=30&scope=" + scope + "&format=" + format + "&q=" + Uri.encode(query);
        status.setText("Buscando en la biblioteca del PC…");
        work(() -> client.request("GET", path, null), value -> {
            if (current != generation || epoch != searchEpoch || !"library".equals(screen)) return;
            books.clear(); JSONArray array = value.getJSONArray("books"); for (int i = 0; i < array.length(); i++) books.add(array.getJSONObject(i));
            total = value.optInt("total");
            if (total > 0 && offset >= total) { offset = ((total - 1) / 30) * 30; loadBooks(); return; }
            bookAdapter.notifyDataSetChanged();
            pageLabel.setText(total == 0 ? "Sin resultados" : (offset + 1) + "–" + (offset + books.size()) + " / " + total);
            previous.setEnabled(offset > 0); next.setEnabled(offset + 30 < total);
            status.setText(total == 0 ? "No hay coincidencias. Prueba otra búsqueda o elige la biblioteca en el PC." : "Biblioteca del PC · " + total + " libros");
        });
    }
    private void openDetails(String id) {
        if (api == null) return; DesktopApi client = api;
        work(() -> client.request("GET", "/api/v1/books/" + id, null), value -> { selected = value; showScreen("details"); });
    }
    private void details(JSONObject item) {
        heading.setText("Detalles"); LinearLayout content = scrollBody();
        LinearLayout top = card(content); ImageView cover = new ImageView(this); cover.setScaleType(ImageView.ScaleType.FIT_CENTER);
        top.addView(cover, new LinearLayout.LayoutParams(-1, dp(250))); loadCover(cover, item);
        TextView title = text(item.optString("title"), 27, ink, false); title.setTypeface(Typeface.create("serif", Typeface.NORMAL)); top.addView(title);
        top.addView(text(item.optString("author"), 18, muted, false));
        String chips = item.optString("format") + (item.optString("language").isEmpty() ? "" : " · " + item.optString("language")); top.addView(text(chips, 14, accent, true));
        spaced(top, button("Abrir libro en el móvil", true, () -> downloadBook(item)), 12);
        spaced(top, button(item.optBoolean("favorite") ? "Quitar de favoritos" : "Añadir a favoritos", false, () -> {
            try { saveMetadata(item, new JSONObject().put("favorite", !item.optBoolean("favorite")), () -> openDetails(item.optString("id"))); }
            catch (Exception ex) { error(ex); }
        }), 9);
        LinearLayout data = card(content); data.addView(text("Información del libro", 18, ink, true));
        String[][] fields = {{"Serie", "series"}, {"ISBN", "isbn"}, {"Año", "year"}, {"Editorial", "publisher"}, {"Estado", "read_status"}, {"Tamaño", "size_label"}};
        for (String[] field : fields) if (!item.optString(field[1]).isEmpty()) data.addView(text(field[0] + " · " + item.optString(field[1]), 15, ink, false));
        JSONArray tags = item.optJSONArray("tags"); if (tags != null && tags.length() > 0) data.addView(text("Etiquetas · " + join(tags), 15, accent, false));
        TextView path = text("Ruta completa en el PC\n" + item.optString("path"), 13, muted, false); path.setTextIsSelectable(true); spaced(data, path, 9);
        spaced(data, button("Editar metadatos", false, () -> metadataDialog(item, null, null)), 12);
        spaced(data, button("Analizar con el PC · Indra OCR", false, () -> postJob("/api/v1/books/" + item.optString("id") + "/analyze", new JSONObject(), job -> {
            metadataDialog(item, job.optJSONObject("metadata"), null);
        })), 9);
        spaced(content, button("Preparar traslado a cuarentena", false, () -> {
            try { postJob("/api/v1/books/" + item.optString("id") + "/quarantine-preview", new JSONObject().put("revision", item.getString("revision")), this::confirmPlan); }
            catch (Exception ex) { error(ex); }
        }), 16);
    }
    private String join(JSONArray array) { ArrayList<String> values = new ArrayList<>(); for (int i = 0; i < array.length(); i++) values.add(array.optString(i)); return TextUtils.join(", ", values); }
    private void saveMetadata(JSONObject item, JSONObject fields, Runnable done) throws Exception {
        fields.put("revision", item.getString("revision"));
        postJob("/api/v1/books/" + item.getString("id") + "/metadata", fields, result -> done.run());
    }
    private void metadataDialog(JSONObject item, JSONObject suggestion, String uploadId) {
        LinearLayout form = column(); form.setPadding(dp(18), dp(8), dp(18), dp(14));
        String[] labels = {"Título", "Autor", "Año", "ISBN", "Serie", "Etiquetas separadas por comas"};
        String[] keys = {"title", "author", "year", "isbn", "series", "tags"};
        String[] remote = {"titulo", "autor", "anio", "isbn", "serie", "tags"};
        EditText[] inputs = new EditText[labels.length];
        for (int i = 0; i < labels.length; i++) {
            String value = item == null ? "" : ("tags".equals(keys[i]) ? join(item.optJSONArray("tags") == null ? new JSONArray() : item.optJSONArray("tags")) : item.optString(keys[i]));
            if (suggestion != null && suggestion.has(remote[i])) value = suggestion.optString(remote[i]);
            form.addView(text(labels[i], 13, muted, true)); inputs[i] = field(labels[i], value); spaced(form, inputs[i], 2);
        }
        CheckBox confirmed = new CheckBox(this); confirmed.setText("He revisado el título, el autor y la edición"); confirmed.setTextColor(ink);
        if (uploadId != null) { form.addView(confirmed); form.addView(text("El original del móvil se conserva. Todavía no se moverá ningún archivo en el PC.", 13, muted, false)); }
        else form.addView(text("Se guardarán datos del catálogo. El archivo del libro no se renombra.", 13, muted, false));
        ScrollView scroll = new ScrollView(this); scroll.addView(form);
        AlertDialog dialog = dialog().setTitle(uploadId == null ? "Revisar metadatos" : "Revisar importación")
            .setView(scroll).setNegativeButton("Cancelar", null).setPositiveButton(uploadId == null ? "Guardar" : "Previsualizar", null).create();
        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view -> {
            try {
                if (inputs[0].getText().toString().trim().isEmpty() || inputs[1].getText().toString().trim().isEmpty()) throw new IOException("Escribe un título y un autor antes de continuar.");
                JSONObject fields = new JSONObject();
                for (int i = 0; i < inputs.length; i++) {
                    String value = inputs[i].getText().toString().trim();
                    if ("tags".equals(keys[i])) { JSONArray tags = new JSONArray(); for (String tag : value.split(",")) if (!tag.trim().isEmpty()) tags.put(tag.trim()); fields.put("tags", tags); }
                    else fields.put(keys[i], value);
                }
                if (uploadId != null) {
                    if (!confirmed.isChecked()) throw new IOException("Marca la confirmación después de revisar los metadatos.");
                    fields.put("confirmed", true); postJob("/api/v1/uploads/" + uploadId + "/import-preview", fields, this::confirmPlan);
                } else saveMetadata(item, fields, () -> openDetails(item.optString("id")));
                dialog.dismiss();
            } catch (Exception ex) { error(ex); }
        }));
        dialog.show();
    }
    private void imports() {
        heading.setText("Importar"); LinearLayout content = scrollBody();
        LinearLayout intro = card(content); intro.addView(text("Del móvil a tu biblioteca", 22, ink, true));
        intro.addView(text("Se enviará una copia al PC. Indra puede analizarla allí. Después revisarás los metadatos y confirmarás el cambio.", 15, muted, false));
        spaced(intro, button("Elegir libro del teléfono", true, () -> {
            Intent choose = new Intent(Intent.ACTION_OPEN_DOCUMENT); choose.addCategory(Intent.CATEGORY_OPENABLE); choose.setType("*/*");
            choose.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
            try { startActivityForResult(choose, 200); } catch (ActivityNotFoundException ex) { error(new Exception("No hay un selector de archivos disponible en Android.")); }
        }), 12);
        LinearLayout incoming = card(content); incoming.addView(text("Bandeja del PC", 19, ink, true));
        incoming.addView(text("Cargando envíos…", 14, muted, false)); int current = generation; DesktopApi client = api;
        work(() -> client.request("GET", "/api/v1/uploads", null), value -> {
            if (current != generation) return;
            incoming.removeAllViews(); incoming.addView(text("Bandeja del PC", 19, ink, true));
            JSONArray rows = value.getJSONArray("uploads");
            if (rows.length() == 0) incoming.addView(text("Aún no has enviado libros desde este móvil.", 15, muted, false));
            for (int i = 0; i < rows.length(); i++) {
                JSONObject row = rows.getJSONObject(i); incoming.addView(text(row.optString("name"), 17, ink, true));
                incoming.addView(text(uploadState(row.optString("state")), 13, muted, false));
                if ("received".equals(row.optString("state")) || "review".equals(row.optString("state"))) {
                    spaced(incoming, button("Analizar en el PC", false, () -> postJob("/api/v1/uploads/" + row.optString("id") + "/analyze", new JSONObject(), result -> {
                        metadataDialog(null, result.optJSONObject("metadata"), row.optString("id"));
                    })), 5);
                    spaced(incoming, button("Revisar metadatos manualmente", false, () -> metadataDialog(null, row.optJSONObject("metadata"), row.optString("id"))), 5);
                }
                spaced(incoming, text("", 2, border, false), 6);
            }
        });
    }
    private String uploadState(String state) {
        if ("completed".equals(state)) return "Importado · original del móvil conservado";
        if ("review".equals(state)) return "Análisis listo · pendiente de revisión";
        if ("interrupted".equals(state)) return "Envío interrumpido · puedes volver a enviar el original";
        return "Recibido en el PC · sin importar todavía";
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if(request==AppUpdates.SETTINGS_REQUEST){status.setText("Permiso revisado. Pulsa Instalar actualización para continuar con la confirmación de Android.");return;}
        if(request==AppUpdates.INSTALL_REQUEST){status.setText(result==RESULT_OK?"Actualización entregada a Android. Abre la nueva versión.":"Instalación cancelada o rechazada · la versión anterior se conserva");return;}
        if (request != 200 || result != RESULT_OK || data == null || data.getData() == null || api == null) return;
        Uri uri = data.getData(); DesktopApi client = api;
        if (transferring) { status.setText("Termina o cancela la transferencia actual."); return; }
        transferring = true; cancelTransfer.setVisibility(View.VISIBLE);
        final int epoch = ++transferEpoch;
        status.setText("Preparando una copia del archivo seleccionado…");
        try {
            transfer = network.submit(() -> {
                File copy = new File(getCacheDir(), "upload-" + UUID.randomUUID().toString() + ".part");
                try {
                    String name = "libro.epub";
                    try (Cursor cursor = getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
                        if (cursor != null && cursor.moveToFirst()) name = cursor.getString(0);
                    }
                    if (name == null || name.contains("/") || name.contains("\\")) throw new IOException("Nombre de archivo no válido");
                    try (InputStream in = getContentResolver().openInputStream(uri); FileOutputStream out = new FileOutputStream(copy)) {
                        if (in == null) throw new IOException("No se pudo abrir el archivo seleccionado");
                        byte[] buffer = new byte[65536]; int count; long total = 0;
                        while ((count = in.read(buffer)) != -1) {
                            if (Thread.currentThread().isInterrupted()) throw new InterruptedIOException("Cancelado");
                            total += count; if (total > DesktopApi.MAX_FILE) throw new IOException("El libro supera los 512 MB");
                            out.write(buffer, 0, count);
                        }
                        out.getFD().sync();
                    }
                    handler.post(() -> { if (!destroyed) status.setText("Enviando la copia al PC…"); });
                    JSONObject receipt = client.upload(copy, name);
                    handler.post(() -> { if (!destroyed && epoch == transferEpoch) { status.setText("Copia recibida y verificada en el PC"); showScreen("import"); Toast.makeText(this, "Original conservado · envío " + receipt.optString("name"), Toast.LENGTH_LONG).show(); } });
                } catch (Exception ex) { handler.post(() -> { if (!destroyed && epoch == transferEpoch) error(ex); }); }
                finally { copy.delete(); handler.post(() -> { if (epoch == transferEpoch) { transferring = false; if (!destroyed) cancelTransfer.setVisibility(View.GONE); } }); }
            });
        } catch (RejectedExecutionException ignored) { transferring = false; cancelTransfer.setVisibility(View.GONE); }
    }
    private void downloadBook(JSONObject item) {
        if (transferring) { status.setText("Termina o cancela la transferencia actual."); return; }
        transferring = true; cancelTransfer.setVisibility(View.VISIBLE);
        final int epoch = ++transferEpoch;
        DesktopApi client = api; status.setText("Descargando una copia verificada del libro…");
        transfer = work(() -> {
            try {
            String name = item.optString("name", "libro");
            if (name.contains("/") || name.contains("\\") || ".".equals(name) || "..".equals(name)) throw new IOException("Nombre de libro no válido");
            File target = new File(new File(new File(getCacheDir(), "books"), UUID.randomUUID().toString().replace("-", "")), name);
            client.download(item.getString("id"), target); return target;
            } finally { handler.post(() -> { if (epoch == transferEpoch) { transferring = false; if (!destroyed) cancelTransfer.setVisibility(View.GONE); } }); }
        }, file -> {
            if (epoch != transferEpoch) return;
            Uri uri = new Uri.Builder().scheme("content").authority(getPackageName() + ".files")
                .appendPath(file.getParentFile().getName()).appendPath(file.getName()).build();
            Intent open = new Intent(Intent.ACTION_VIEW); open.setDataAndType(uri, getContentResolver().getType(uri));
            open.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION); open.setClipData(ClipData.newRawUri("Libro", uri));
            try { startActivity(Intent.createChooser(open, "Abrir copia del libro")); status.setText("Copia verificada · original conservado en el PC"); }
            catch (ActivityNotFoundException ex) { error(new Exception("Instala un lector compatible con " + item.optString("format") + " para abrir este libro. El original sigue en el PC.")); }
        });
        if (transfer == null) { transferring = false; cancelTransfer.setVisibility(View.GONE); }
    }
    private void postJob(String path, JSONObject body, Done<JSONObject> done) {
        if (api == null) return; DesktopApi client = api; status.setText("Solicitud enviada al PC…");
        work(() -> client.request("POST", path, body), value -> watchJob(value.getString("job_id"), done, 0));
    }
    private void watchJob(String id, Done<JSONObject> done, int attempts) {
        if (destroyed || api == null) return; DesktopApi client = api;
        work(() -> client.request("GET", "/api/v1/jobs/" + id, null), value -> {
            String state = value.optString("state"); status.setText(value.optString("message", "Procesando en el PC…"));
            if (!resumed) { status.setText("Consulta el resultado de la tarea en Actividad."); return; }
            if ("completed".equals(state)) done.accept(value.optJSONObject("result") == null ? new JSONObject() : value.getJSONObject("result"));
            else if ("failed".equals(state) || "cancelled".equals(state) || "interrupted".equals(state))
                dialog().setTitle("Operación del PC").setMessage(value.optString("message")).setPositiveButton("Entendido", null).show();
            else if (attempts < 600 && resumed) handler.postDelayed(() -> watchJob(id, done, attempts + 1), 1000);
            else status.setText("La tarea continúa en el PC. Consulta Actividad.");
        });
    }
    private void confirmPlan(JSONObject plan) {
        String id = plan.optString("plan_id", plan.optString("id"));
        if (id.isEmpty()) { error(new Exception("No se pudo obtener el plan de cambios")); return; }
        boolean quarantine = "quarantine".equals(plan.optString("action")) || "mobile_quarantine".equals(plan.optString("kind"));
        String message = (quarantine ? "Mover a la cuarentena recuperable del PC:\n\n" : "Importar una copia en la biblioteca del PC:\n\n") + plan.optString("name") +
            "\n\nSe verificará de nuevo la firma del archivo. No se reemplazará ningún libro existente.";
        dialog().setTitle("Confirmar plan").setMessage(message).setNegativeButton("Cancelar", null)
            .setPositiveButton("Confirmar", (d, which) -> {
                try { postJob("/api/v1/plans/" + id, new JSONObject().put("confirmed", true), value -> { status.setText("Cambio completado y registrado"); showScreen("activity"); }); }
                catch (Exception ex) { error(ex); }
            }).show();
    }
    private void activity() {
        heading.setText("Actividad"); LinearLayout actions = row(); actions.setPadding(dp(14), dp(5), dp(14), dp(9));
        Button plans = button("Planes pendientes", false, this::pendingPlans); actions.addView(plans, new LinearLayout.LayoutParams(0, -2, 1));
        Button undo = button("Deshacer", false, this::undo); LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(0, -2, 1); p.leftMargin = dp(8); actions.addView(undo, p); body.addView(actions);
        ListView list = new ListView(this); list.setDivider(null); list.setPadding(dp(14), 0, dp(14), dp(10)); jobAdapter = new JobAdapter(); list.setAdapter(jobAdapter);
        list.setOnItemClickListener((parent, view, position, id) -> jobDetails(jobs.get(position))); body.addView(list, new LinearLayout.LayoutParams(-1, 0, 1));
        loadJobs(true); handler.removeCallbacks(activityRefresh); handler.postDelayed(activityRefresh, 1800);
    }
    private void loadJobs(boolean announce) {
        if (api == null || !"activity".equals(screen) || jobsLoading) return; int current = generation; DesktopApi client = api;
        jobsLoading = true;
        Future<?> request = work(() -> {
            try { return client.request("GET", "/api/v1/jobs", null); }
            finally { handler.post(() -> jobsLoading = false); }
        }, value -> {
            if (current != generation || !"activity".equals(screen)) return;
            jobs.clear(); JSONArray rows = value.getJSONArray("jobs"); for (int i = 0; i < rows.length(); i++) jobs.add(rows.getJSONObject(i));
            jobAdapter.notifyDataSetChanged(); if (announce) status.setText(jobs.isEmpty() ? "Todavía no has solicitado ninguna tarea desde este móvil." : "Historial conservado en el PC");
        });
        if (request == null) jobsLoading = false;
    }
    private void jobDetails(JSONObject job) {
        String state = job.optString("state");
        if ("queued".equals(state) || "running".equals(state)) {
            dialog().setTitle("Tarea en el PC").setMessage(job.optString("message"))
                .setNegativeButton("Cerrar", null).setPositiveButton("Cancelar tarea", (d, w) -> {
                    DesktopApi client = api; work(() -> client.request("POST", "/api/v1/jobs/" + job.optString("id") + "/cancel", new JSONObject()), value -> loadJobs(false));
                }).show(); return;
        }
        JSONObject result = job.optJSONObject("result");
        if (result != null && result.has("plan_id") && result.optBoolean("preview_only")) { confirmPlan(result); return; }
        if (result != null && result.has("upload_id") && result.has("metadata")) { metadataDialog(null, result.optJSONObject("metadata"), result.optString("upload_id")); return; }
        if (result != null && result.has("book_id") && result.has("metadata")) {
            DesktopApi client = api; work(() -> client.request("GET", "/api/v1/books/" + result.optString("book_id"), null), value -> metadataDialog(value, result.optJSONObject("metadata"), null)); return;
        }
        dialog().setTitle("Operación del PC").setMessage(job.optString("message") + "\n\nEstado: " + state).setPositiveButton("Cerrar", null).show();
    }
    private void pendingPlans() {
        DesktopApi client = api;
        work(() -> client.request("GET", "/api/v1/plans", null), value -> {
            JSONArray plans = value.getJSONArray("plans"); if (plans.length() == 0) { status.setText("No hay planes pendientes de este móvil."); return; }
            String[] names = new String[plans.length()]; for (int i = 0; i < names.length; i++) names[i] = plans.getJSONObject(i).optString("name") + " · " + plans.getJSONObject(i).optString("state");
            dialog().setTitle("Revisar o reanudar un plan").setItems(names, (dialog, index) -> { try { confirmPlan(plans.getJSONObject(index)); } catch (Exception ex) { error(ex); } }).setNegativeButton("Cerrar", null).show();
        });
    }
    private void undo() {
        DesktopApi client = api;
        work(() -> client.request("GET", "/api/v1/undo", null), value -> {
            if (!value.optBoolean("available")) { status.setText("No hay una operación móvil reciente que pueda deshacerse aquí. Revisa el PC."); return; }
            dialog().setTitle("Deshacer en el PC").setMessage("¿Restaurar los archivos de la última operación de este móvil? Se mantendrán pendientes los que no puedan recuperarse.")
                .setNegativeButton("Cancelar", null).setPositiveButton("Restaurar", (d, w) -> { try { postJob("/api/v1/undo", new JSONObject().put("confirmed", true).put("batch", value.getString("batch")), result -> showScreen("activity")); } catch (Exception ex) { error(ex); } }).show();
        });
    }
    private void loadCover(ImageView view, JSONObject item) {
        String id = item.optString("id"), key = id + ":" + item.optString("revision"); view.setTag(key); view.setImageResource(R.drawable.ic_library);
        Bitmap cached = covers.get(key); if (cached != null) { view.setImageBitmap(cached); return; }
        if (api == null || !loadingCovers.add(key)) return; DesktopApi client = api;
        try { coverNetwork.submit(() -> {
            try {
                byte[] data = client.cover(id); Bitmap bitmap = data == null ? null : BitmapFactory.decodeByteArray(data, 0, data.length);
                if (bitmap != null) { covers.put(key, bitmap); handler.post(() -> { if (!destroyed && key.equals(view.getTag())) view.setImageBitmap(bitmap); }); }
            } catch (Exception ignored) { }
            finally { loadingCovers.remove(key); }
        }); } catch (RejectedExecutionException ignored) { loadingCovers.remove(key); }
    }
    private final class BookAdapter extends BaseAdapter {
        @Override public int getCount() { return books.size(); }
        @Override public Object getItem(int position) { return books.get(position); }
        @Override public long getItemId(int position) { return books.get(position).optString("id").hashCode(); }
        @Override public View getView(int position, View reusable, android.view.ViewGroup parent) {
            LinearLayout outer; Holder holder;
            if (reusable instanceof LinearLayout && reusable.getTag() instanceof Holder) { outer = (LinearLayout) reusable; holder = (Holder) reusable.getTag(); }
            else {
                outer = column(); outer.setPadding(dp(3), dp(5), dp(3), dp(5)); LinearLayout line = row(); line.setPadding(dp(12), dp(12), dp(10), dp(12)); line.setBackground(shape(surface, border, 16)); outer.addView(line);
                holder = new Holder(); holder.cover = new ImageView(MainActivity.this); holder.cover.setScaleType(ImageView.ScaleType.FIT_CENTER); line.addView(holder.cover, new LinearLayout.LayoutParams(dp(74), dp(106)));
                LinearLayout description = column(); LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(0, -2, 1); p.leftMargin = dp(13); line.addView(description, p);
                holder.title = text("", 19, ink, false); holder.title.setTypeface(Typeface.create("serif", Typeface.NORMAL)); holder.title.setMaxLines(3); holder.title.setEllipsize(TextUtils.TruncateAt.END); description.addView(holder.title);
                holder.author = text("", 14, muted, false); holder.author.setMaxLines(2); description.addView(holder.author); holder.extra = text("", 12, accent, false); description.addView(holder.extra);
                holder.favorite = new Icon("heart", accent); holder.favorite.setFocusable(true); line.addView(holder.favorite, new LinearLayout.LayoutParams(dp(48), dp(48))); outer.setTag(holder);
            }
            JSONObject item = books.get(position); holder.title.setText(item.optString("title")); holder.author.setText(item.optString("author"));
            holder.extra.setText(item.optString("format") + (item.optString("series").isEmpty() ? "" : " · " + item.optString("series")));
            holder.favorite.setAlpha(item.optBoolean("favorite") ? 1f : 0.45f); holder.favorite.setContentDescription((item.optBoolean("favorite") ? "Quitar de favoritos: " : "Añadir a favoritos: ") + item.optString("title"));
            holder.favorite.setOnClickListener(v -> { try { saveMetadata(item, new JSONObject().put("favorite", !item.optBoolean("favorite")), MainActivity.this::loadBooks); } catch (Exception ex) { error(ex); } });
            outer.setOnClickListener(v -> openDetails(item.optString("id")));
            outer.setFocusable(true); outer.setContentDescription(item.optString("title") + ", " + item.optString("author"));
            loadCover(holder.cover, item); return outer;
        }
    }
    private static final class Holder { ImageView cover; TextView title, author, extra; Icon favorite; }
    private final class JobAdapter extends BaseAdapter {
        public int getCount() { return jobs.size(); } public Object getItem(int position) { return jobs.get(position); }
        public long getItemId(int position) { return jobs.get(position).optString("id").hashCode(); }
        public View getView(int position, View convert, android.view.ViewGroup parent) {
            LinearLayout outer = column(); outer.setPadding(dp(2), dp(5), dp(2), dp(5)); LinearLayout box = column(); box.setPadding(dp(15), dp(12), dp(15), dp(12)); box.setBackground(shape(surface, border, 15)); outer.addView(box);
            JSONObject job = jobs.get(position); String kind = job.optString("kind");
            HashMap<String, String> names = new HashMap<>(); names.put("metadata", "Metadatos"); names.put("analyze", "Análisis de libro"); names.put("analyze_upload", "Análisis de envío"); names.put("preview", "Previsualización"); names.put("apply_plan", "Aplicación de plan"); names.put("undo", "Restauración");
            box.addView(text(names.containsKey(kind) ? names.get(kind) : kind, 17, ink, true)); box.addView(text(job.optString("message"), 14, muted, false));
            HashMap<String, String> states = new HashMap<>(); states.put("queued", "En cola"); states.put("running", "En curso"); states.put("completed", "Completada"); states.put("failed", "Necesita atención"); states.put("cancelled", "Cancelada"); states.put("interrupted", "Interrumpida");
            box.addView(text(states.containsKey(job.optString("state")) ? states.get(job.optString("state")) : job.optString("state"), 12, accent, true)); return outer;
        }
    }
    private final class Icon extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG); private final String name; private final int color;
        Icon(String name, int color) { super(MainActivity.this); this.name = name; this.color = color; setMinimumWidth(dp(24)); setMinimumHeight(dp(24)); }
        @Override protected void onDraw(Canvas canvas) {
            super.onDraw(canvas); canvas.save(); float side = Math.min(getWidth(), getHeight()); canvas.translate((getWidth() - side) / 2f, (getHeight() - side) / 2f); canvas.scale(side / 32f, side / 32f);
            paint.setColor(color); paint.setStyle(Paint.Style.STROKE); paint.setStrokeWidth(1.8f); paint.setStrokeCap(Paint.Cap.ROUND); paint.setStrokeJoin(Paint.Join.ROUND);
            Path p = new Path();
            if ("heart".equals(name)) { p.moveTo(16, 26); p.cubicTo(2, 17, 3, 5, 11, 7); p.cubicTo(14, 7, 15, 9, 16, 11); p.cubicTo(20, 3, 29, 7, 28, 14); p.cubicTo(28, 19, 22, 23, 16, 26); canvas.drawPath(p, paint); }
            else if ("book".equals(name)) { p.moveTo(5, 6); p.cubicTo(11, 5, 13, 7, 16, 9); p.cubicTo(19, 7, 23, 5, 27, 6); p.lineTo(27, 26); p.cubicTo(21, 25, 18, 27, 16, 29); p.cubicTo(12, 26, 9, 25, 5, 26); p.close(); canvas.drawPath(p, paint); canvas.drawLine(16, 9, 16, 27, paint); }
            else if ("upload".equals(name)) { canvas.drawLine(16, 23, 16, 5, paint); canvas.drawLine(10, 11, 16, 5, paint); canvas.drawLine(22, 11, 16, 5, paint); p.moveTo(5, 21); p.lineTo(5, 27); p.lineTo(27, 27); p.lineTo(27, 21); canvas.drawPath(p, paint); }
            else if ("history".equals(name)) { canvas.drawCircle(16, 16, 11, paint); canvas.drawLine(16, 9, 16, 17, paint); canvas.drawLine(16, 17, 22, 20, paint); }
            else if ("settings".equals(name)) { canvas.drawCircle(16, 16, 4, paint); canvas.drawCircle(16, 16, 10, paint); for (int i = 0; i < 8; i++) { double angle = i * Math.PI / 4; canvas.drawLine((float)(16 + 10 * Math.cos(angle)), (float)(16 + 10 * Math.sin(angle)), (float)(16 + 13 * Math.cos(angle)), (float)(16 + 13 * Math.sin(angle)), paint); } }
            else { canvas.drawArc(6, 6, 26, 26, 35, 295, false, paint); canvas.drawLine(26, 5, 26, 12, paint); canvas.drawLine(20, 12, 26, 12, paint); }
            canvas.restore();
        }
    }
}
