package com.erzod31.manageyourlibrary;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

final class SecretStore {
    private final SharedPreferences preferences;
    private final String alias;
    SecretStore(Context context) {
        preferences = context.getSharedPreferences("connection", Context.MODE_PRIVATE);
        alias = context.getPackageName() + ".connection.key";
    }
    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
        if (!store.containsAlias(alias)) {
            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build());
            generator.generateKey();
        }
        return ((KeyStore.SecretKeyEntry) store.getEntry(alias, null)).getSecretKey();
    }
    void save(String url, String token) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, key());
        cipher.updateAAD(url.getBytes(StandardCharsets.UTF_8));
        String value = Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":" +
            Base64.encodeToString(cipher.doFinal(token.getBytes(StandardCharsets.UTF_8)), Base64.NO_WRAP);
        if (!preferences.edit().putString("url", url).putString("credential", value).commit())
            throw new IllegalStateException("No se pudo guardar la conexión de forma segura");
    }
    String url() { return preferences.getString("url", ""); }
    String token() throws Exception {
        String value = preferences.getString("credential", "");
        if (value.isEmpty()) return "";
        String[] parts = value.split(":", 2);
        if (parts.length != 2) throw new IllegalStateException("Vuelve a vincular el móvil");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)));
        cipher.updateAAD(url().getBytes(StandardCharsets.UTF_8));
        return new String(cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), StandardCharsets.UTF_8);
    }
    void clear() { preferences.edit().remove("credential").remove("url").apply(); }
}
