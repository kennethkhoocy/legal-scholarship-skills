@echo off
echo Building Citation Restyle Tool...
echo.

pip install pyinstaller anthropic python-docx lxml pydantic >nul 2>&1

pyinstaller --onefile --windowed ^
  --name "Citation Restyle Tool" ^
  --add-data "..\..\references\styles;styles" ^
  --add-data "..\..\scripts\core\docx_support;docx_support" ^
  --hidden-import anthropic ^
  --hidden-import pydantic ^
  --hidden-import lxml ^
  --hidden-import docx ^
  restyle_app.py

echo.
if exist "dist\Citation Restyle Tool.exe" (
    echo Build successful!
    echo Output: dist\Citation Restyle Tool.exe
) else (
    echo Build failed. Check output above for errors.
)
pause
