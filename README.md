# PetPass MX

Demo de pasaporte digital para mascotas con Streamlit, SQLite local y Supabase Cloud.

## Correr local con SQLite

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Sin credenciales de Supabase, la app usa `data/petpass.db` automaticamente.

## Configurar Supabase V3

1. Crea un proyecto en Supabase.
2. En SQL Editor ejecuta `supabase_schema.sql`.
3. En SQL Editor ejecuta `supabase_v3_security.sql`.
4. En Authentication > Providers > Email, activa email/password.
5. Para demo rápida, desactiva temporalmente confirmación de email. Si la dejas activa, confirma el email antes de iniciar sesión.
6. Verifica que exista el bucket `pet-photos`.
   En V3 se protege la base de datos con RLS; Storage `pet-photos` queda temporalmente en modo demo hasta implementar policies específicas.
7. Copia `.streamlit/secrets.toml.example` a `.streamlit/secrets.toml`.
8. Llena:

```toml
SUPABASE_URL = "https://TU-PROYECTO.supabase.co"
SUPABASE_KEY = "TU-ANON-OR-PUBLISHABLE-KEY"
```

## Probar V3 local

1. Corre `streamlit run app.py`.
2. Entra a `Crear cuenta / registrar clínica`.
3. Crea una clínica con email y password.
4. Cierra sesión.
5. Inicia sesión con ese usuario.
6. Crea tutor, mascota con foto y vacuna.
7. Revisa Dashboard, Expediente, QR, PDF y WhatsApp.
8. Crea otra cuenta/clínica y confirma que no ve los datos de la primera.
9. Entra a `Usar demo pública` y valida que muestra advertencia de datos ficticios.

## Streamlit Community Cloud

1. Sube el proyecto a GitHub.
2. En Streamlit Cloud crea una app nueva apuntando a `app.py`.
3. En Advanced settings agrega:

```toml
SUPABASE_URL = "https://TU-PROYECTO.supabase.co"
SUPABASE_KEY = "TU-ANON-OR-PUBLISHABLE-KEY"
```

4. Deploy.
5. Prueba registro, login y demo pública.

## Notas de seguridad

- V3 activa RLS en `clinicas`, `clinica_usuarios`, `tutores`, `mascotas` y `vacunas`.
- Las operaciones reales se filtran por `clinica_usuarios.user_id = auth.uid()`.
- Storage usa rutas `{clinica_id}/{mascota_id}/{filename}`, pero `pet-photos` queda temporalmente en modo demo hasta implementar policies específicas.
- Demo pública queda limitada a la clínica `PETPASS-DEMO` y debe usarse solo con datos ficticios.

## Limitaciones pendientes

- No hay recuperación de contraseña.
- No hay invitación de usuarios adicionales desde UI.
- No hay roles avanzados más allá de `admin`.
- PDFs se generan local/temporalmente.
- WhatsApp sigue siendo solo link web, no API.
