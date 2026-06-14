# PetPass MX

Demo de pasaporte digital para mascotas con Streamlit.

## Correr local con SQLite

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Sin credenciales de Supabase, la app usa `data/petpass.db` automaticamente.

## Configurar Supabase

1. Crea un proyecto en Supabase.
2. Abre SQL Editor.
3. Ejecuta el archivo `supabase_schema.sql`.
4. Verifica que exista el bucket publico `pet-photos` en Storage.
5. Copia `.streamlit/secrets.toml.example` a `.streamlit/secrets.toml`.
6. Llena:

```toml
SUPABASE_URL = "https://TU-PROYECTO.supabase.co"
SUPABASE_KEY = "TU-ANON-OR-PUBLISHABLE-KEY"
```

Con esos secrets, la app entra en modo Supabase y pide codigo de clinica.

## Streamlit Community Cloud

1. Sube el proyecto a GitHub.
2. En Streamlit Cloud crea una app nueva apuntando a `app.py`.
3. En Advanced settings agrega los secrets:

```toml
SUPABASE_URL = "https://TU-PROYECTO.supabase.co"
SUPABASE_KEY = "TU-ANON-OR-PUBLISHABLE-KEY"
```

4. Deploy.
5. Entra con `PETPASS-DEMO` o usa `Usar demo publica`.

## Probar la demo

1. Entra a `Datos demo`.
2. Carga datos demo.
3. Crea tutor, mascota con foto y vacuna.
4. Revisa Dashboard y Expediente.
5. Genera QR/PDF y descarga el PDF.
6. Abre el link de WhatsApp.

Las fotos locales se guardan en `storage/photos/`. En Supabase se suben al bucket `pet-photos`.

## Limitaciones V2

- RLS queda pendiente; esta V2 es demo, no produccion.
- No hay login real ni roles.
- Los PDFs se generan local/temporalmente.
- No hay WhatsApp API, solo link web.
