# PetPass MX

## Crear entorno virtual

```powershell
python -m venv .venv
```

## Activar entorno

```powershell
.venv\Scripts\activate
```

## Instalar dependencias

```powershell
pip install -r requirements.txt
```

## Correr app

```powershell
streamlit run app.py
```

## Cómo probar la demo

1. Abre la app.
2. Entra a `Datos demo` y presiona `Cargar datos demo`.
3. Revisa `Dashboard`.
4. Crea una mascota y sube una foto opcional.
5. Entra a `Expediente`, selecciona una mascota y genera QR/PDF.
6. Abre el link de WhatsApp.

Las fotos de mascotas se guardan en `storage/photos/`.
