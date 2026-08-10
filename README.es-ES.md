

**Idiomas:** [English](README.md) | [Español](README.es-ES.md)

# Asistente CAD de SolidWorks y Servidor MCP

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-blue?logo=windows)](https://www.microsoft.com/windows)
[![SolidWorks](https://img.shields.io/badge/SolidWorks-2019--2026-red)](https://www.solidworks.com/)
[![Coverage](https://codecov.io/gh/andrewbartels1/SolidworksMCP-python/branch/main/graph/badge.svg)](https://codecov.io/gh/andrewbartels1/SolidworksMCP-python)

Servidor MCP de Python para la automatización de SolidWorks con 109 herramientas, más una capa opcional de agente/pruebas de prompts para flujos de trabajo asistidos por IA.

## Descripción General

> ⚠️ **Estado del proyecto:** Este proyecto está en construcción activa. Las características, API, documentación y pasos de configuración pueden cambiar a medida que se finalicen las implementaciones de Python y la interfaz de usuario. Este es un producto de pasatiempo/investigación, ¡no dudes en crear un issue si tienes preguntas o comentarios! ⚠️

Este proyecto se centra en la automatización práctica de SolidWorks con un ciclo amigable para la IA:

1. describir la intención
2. generar un plan
3. ejecutar herramientas MCP
4. inspeccionar resultados
5. iterar

Incluye:

- entorno de ejecución principal de MCP para la ejecución de herramientas de SolidWorks
- enrutamiento COM/VBA y envoltorios de seguridad para adaptadores
- cobertura de herramientas en modelado, bocetos, planos, análisis, exportación, automatización, plantillas y macros
- utilidades opcionales de orquestación/pruebas de agentes en `src/solidworks_mcp/agents/`

## Soporte Actual

- Automatización COM de Windows + SolidWorks para el ciclo principal de CAD.
- Herramientas de modelado, bocetos, planos, análisis, exportación, automatización, plantillas y macros.
- Sincronización de la vista previa de la interfaz Prefab desde la ventana de visualización activa como PNG.

## No disponible aún / Simulado

- La salida del adaptador simulado es ficticia y no debe considerarse como un dato técnico de ingeniería.
- Transmisión en vivo de la ventana de visualización 3D en la interfaz.
- Validación de interferencias a nivel de punto de control en el ejecutor de la interfaz.

## Funcionamiento Verificado (Configuración en Windows)

Esta es la ruta de configuración validada de extremo a extremo:

1. Instalar Python desde python.org (instalador de Windows).
2. Habilitar **Agregar python.exe a PATH** durante la instalación.
3. Instalar este proyecto en un `.venv` local.
4. Iniciar MCP desde `.venv\Scripts\python.exe` (no desde WSL).

Cuando esto es correcto, los registros de inicio muestran:

- `Platform: Windows`
- `SolidWorks COM interface is available`
- `Registered ... SolidWorks tools` (la cantidad varía a medida que las herramientas evolucionan)
- `Connected to SolidWorks`

## Requisitos

- Windows 10/11 para automatización COM real de SolidWorks.
- Python 3.13+ desde python.org.
- Git.
- SolidWorks instalado e iniciado al menos una vez.

Linux/WSL es útil para documentación/pruebas/modo simulado, pero no para automatización COM directa.

## Inicio Rápido (Windows, python.org)

```powershell
git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
cd SolidworksMCP-python

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e .
```

Iniciar servidor manualmente:

```powershell
.\.venv\Scripts\python.exe -m solidworks_mcp.server
```

O usar el script de ayuda (abre SolidWorks primero):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-mcp.ps1 --real --year 2026
```

> **Advertencia de modo simulado** — ejecutar `run-mcp.ps1` sin `--real` inicia el
> servidor en modo simulado. Todas las respuestas de las herramientas son ficticias; nada interactúa
> con SolidWorks. Pasa siempre `--real --year <año>` para automatización en vivo.

## Comandos de Desarrollo

Usa el script de ayuda para flujos de trabajo comunes:

```powershell
.\dev-commands.ps1
```

Comandos comunes:

- `dev-install` - instalar/actualizar entorno de desarrollo local
- `dev-test` - ejecutar suite de pruebas estándar (subconjunto seguro para CI)
- `dev-test-full` - ejecutar suite de pruebas completa (incluye rutas de humo/integración)
- `dev-lint` - verificaciones de lint
- `dev-format` - formatear código
- `dev-docs-build` - compilar sitio de documentación una vez
- `dev-docs-strict` - compilación estricta de documentación (falla ante advertencias)
- `dev-docs-audit` - generar informe de auditoría de documentación en `.generated/docs`

### Réplica local de CI (Docker)

Para replicar localmente la CI de GitHub Actions (Ubuntu + entorno conda desde `solidworks_mcp.yml` + `make test`), ejecuta:

```powershell
.\run-ci-local.ps1
```

La primera ejecución compila la imagen. Vuelve a ejecutar sin recompilar cuando solo se ejecuten pruebas:

```powershell
.\run-ci-local.ps1 -NoBuild
```

## Configuración de MCP para VS Code (Windows)

Establece tu configuración de MCP de usuario (`%APPDATA%\Code\User\mcp.json`) en:

```json
{
  "servers": {
    "solidworks-mcp-server": {
      "type": "stdio",
      "command": "powershell",
      "args": [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "C:\\path\\to\\SolidworksMCP-python\\run-mcp.ps1",
        "--real",
        "--year",
        "2026"
      ]
  },
  "inputs": []
}
```

Reemplaza la ruta del script con la ruta de tu repositorio local. Las banderas `--real --year 2026` inician el servidor en modo de automatización COM en vivo (requiere SolidWorks abierto). Omítelas para el modo simulado.

## Configuración de MCP para LM Studio (Windows)

Configura tu archivo de configuración de MCP de LM Studio para incluir este servidor (LM Studio espera `mcpServers`):

```json
{
  "mcpServers": {
    "solidworks-mcp-server": {
      "command": "powershell",
      "args": [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "C:\\path\\to\\SolidworksMCP-python\\run-mcp.ps1"
      ]
    }
  }
}
```

Entrada alternativa directa con Python:

```json
{
  "mcpServers": {
    "solidworks-mcp-server": {
      "command": "C:\\path\\to\\SolidworksMCP-python\\.venv\\Scripts\\python.exe",
      "args": ["-m", "solidworks_mcp.server"]
    }
  }
}
```

Después de guardar, reinicia LM Studio para que recargue los servidores MCP.

## Soluciones Comunes en Windows

Si no se encuentra `python`:

```powershell
python --version
```

Si esto abre la Microsoft Store o falla, reinstala Python desde python.org y habilita PATH.

Si el inicio falla con `ModuleNotFoundError: solidworks_mcp`:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

Si el inicio falla con `ModuleNotFoundError: fastmcp`:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

## Documentación

- Sitio principal de documentación: <https://andrewbartels1.github.io/SolidworksMCP-python/>
- Inicio/visión general: [docs/index.md](docs/index.md)

Secciones clave de la documentación:

- Primeros pasos: [docs/getting-started](docs/getting-started)
- Guía del servidor MCP: [docs/user-guide](docs/user-guide)
- Catálogo de herramientas: [docs/user-guide/tool-catalog](docs/user-guide/tool-catalog)
- Agentes y habilidades: [docs/agents](docs/agents)
- Planificación/hoja de ruta: [docs/planning](docs/planning)

Enlaces directos:

- [Instalación](docs/getting-started/installation.md)
- [Inicio Rápido](docs/getting-started/quickstart.md)
- [Tutorial: Construcción de ensamblaje de junta universal](docs/getting-started/tutorials/u-joint-assembly-build.md)
- [Rutas de tutoriales](docs/getting-started/tutorial-tracks.md)
- [Panel de control de la interfaz Prefab](docs/getting-started/prefab-ui-dashboard.md)
- [Configuración de MCP para VS Code](docs/getting-started/vscode-mcp-setup.md)
- [Arquitectura](docs/user-guide/architecture.md)
- [Agentes y pruebas de prompts](docs/agents/agents-and-testing.md)
- [PydanticAI y esquemas](docs/agents/pydantic-ai-and-schemas.md)

## Licencia

Licencia MIT. Consulta [LICENSE](LICENSE).
