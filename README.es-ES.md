

**Idiomas:** [English](README.md) | [Español](README.es-ES.md)

# Asistente CAD de SolidWorks y Servidor MCP

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-blue?logo=windows)](https://www.microsoft.com/windows)
[![SolidWorks](https://img.shields.io/badge/tested%20on-SolidWorks%202026-red)](https://www.solidworks.com/)
[![Coverage](https://codecov.io/gh/andrewbartels1/SolidworksMCP-python/branch/main/graph/badge.svg)](https://codecov.io/gh/andrewbartels1/SolidworksMCP-python)

Servidor MCP de Python para la automatización de SolidWorks con 151 herramientas, más una capa opcional de agente/pruebas de prompts para flujos de trabajo asistidos por IA.

## Descripción General

> **¿Lo has probado?** Cuéntanos qué funcionó y qué no en un [issue de comentarios](https://github.com/andrewbartels1/SolidworksMCP-python/issues/new?template=feedback.yml). Los informes de instalaciones reales deciden qué se corrige primero.

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
- Probado en SolidWorks 2026. Las versiones anteriores pueden funcionar, pero no se han probado.
- Herramientas de modelado, bocetos, planos, análisis, exportación, automatización, plantillas y macros.
- Sincronización de la vista previa de la interfaz Prefab desde la ventana de visualización activa como PNG.

## No disponible aún / Simulado

- La salida del adaptador simulado es ficticia y no debe considerarse como un dato técnico de ingeniería.
- Transmisión en vivo de la ventana de visualización 3D en la interfaz.
- Validación de interferencias a nivel de punto de control en el ejecutor de la interfaz.

## Instalación

Necesitas Windows 10 u 11 y SolidWorks (abierto al menos una vez). En PowerShell, instala [uv](https://docs.astral.sh/uv/), abre una ventana nueva de PowerShell y ejecuta la configuración guiada:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uvx solidworks-mcp-python setup
```

uv descarga Python 3.13 y el servidor desde PyPI por sí solo; no hace falta clonar nada. La configuración guiada:

1. encuentra tu versión de SolidWorks y los clientes MCP de tu PC: Claude Desktop, Claude Code, VS Code, Cursor y LM Studio;
2. te deja elegir qué clientes conectar;
3. inicia el servidor una vez para comprobar que lista sus herramientas (en modo simulado, sin tocar SolidWorks);
4. añade una entrada `solidworks` a cada cliente elegido y te dice qué reiniciar.

Solo cambia la entrada `solidworks` de cada configuración, hace antes una copia de seguridad y nunca muestra ni cambia tus otros servidores.

**Para comprobarlo:** abre SolidWorks, reinicia tu cliente y pregunta *"¿Qué modelo está abierto en SolidWorks?"*

El paquete se llama `solidworks-mcp-python`. `uvx solidworks-mcp` instala otro proyecto distinto. Para trabajar en el propio servidor, [instala desde un clon](https://andrewbartels1.github.io/SolidworksMCP-python/getting-started/installation/#install-from-source).

## Conectar un cliente a mano

Cada cliente ejecuta `uvx solidworks-mcp-python`. Si un cliente no encuentra `uvx`, usa su ruta completa, de `(Get-Command uvx).Source`.

Claude Desktop (`claude_desktop_config.json`) y LM Studio (`%USERPROFILE%\.lmstudio\mcp.json`):

```json
{
  "mcpServers": {
    "solidworks": {
      "command": "uvx",
      "args": ["solidworks-mcp-python"]
    }
  }
}
```

VS Code (`%APPDATA%\Code\User\mcp.json`):

```json
{
  "servers": {
    "solidworks": {
      "type": "stdio",
      "command": "uvx",
      "args": ["solidworks-mcp-python"]
    }
  }
}
```

Claude Code:

```powershell
claude mcp add --scope user solidworks -- uvx solidworks-mcp-python
```

Para el modo simulado, que no necesita SolidWorks, usa `"args": ["solidworks-mcp-python", "--mock"]`. Linux/WSL sirve para documentación, pruebas y modo simulado, pero no para automatización COM.

## Comandos de Desarrollo

Desde un clon del repositorio, usa el script de ayuda para flujos de trabajo comunes:

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
.\scripts\run-ci-local.ps1
```

La primera ejecución compila la imagen. Vuelve a ejecutar sin recompilar cuando solo se ejecuten pruebas:

```powershell
.\scripts\run-ci-local.ps1 -NoBuild
```

## Soluciones Comunes en Windows

Si `uvx` no se encuentra después de instalar uv, abre una ventana nueva de PowerShell. Más soluciones en [Troubleshooting](https://andrewbartels1.github.io/SolidworksMCP-python/getting-started/installation/#troubleshooting).

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
- [Configuración de MCP para VS Code](docs/getting-started/vscode-mcp-setup.md)
- [Arquitectura](docs/user-guide/architecture.md)
- [Agentes y pruebas de prompts](docs/agents/agents-and-testing.md)
- [PydanticAI y esquemas](docs/agents/pydantic-ai-and-schemas.md)

## Licencia

Licencia MIT. Consulta [LICENSE](LICENSE).
