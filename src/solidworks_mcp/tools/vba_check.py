"""Check that VBA source reaches SolidWorks and nothing else (restricted mode).

A macro runs inside SolidWorks with the user's Windows rights, so the only
way to limit one is to read it first. :func:`check_vba` allows a name only
when it is known to be safe; anything else is refused:

- outside a member access: a VBA keyword, a safe built-in (maths, text,
  conversions, dates, ``MsgBox``, ``InputBox``, ``Err``, ``Debug``), a
  ``vb`` constant, a name the source declares, a SolidWorks enum or enum
  value, a SolidWorks type name, or ``Application`` when it is
  ``Application.SldWorks``;
- after a ``.``: a member of the installed SolidWorks type library that
  isn't in :data:`BLOCKED_MEMBERS` or under :data:`BLOCKED_PREFIXES`, a
  member of VBA's own ``Err``/``Debug``/``Collection`` objects, or a member
  the source declares (a ``Type`` field, an ``Enum`` value).

VBA can only call a name that isn't written in the source through
``CallByName``, ``CreateObject``/``GetObject``, ``Declare`` or
``Application``, which are refused, so checking the written names covers
what the macro can reach. Comments and quoted text are ignored. This is a
check of the source, not a sandbox: the docs say what it can't promise.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

#: VBA keywords and types.
KEYWORDS = frozenset(
    """
    sub function end dim as set let if then else elseif for each in to step
    next do loop while wend until select case is with exit call const redim
    preserve private public static global option explicit base compare text
    binary not and or xor mod like eqv imp new byval byref optional paramarray
    variant object integer long longlong longptr single double string boolean
    date byte currency decimal any goto gosub return on error resume true
    false nothing empty null type enum property me typeof attribute vb_name
    stop
    """.split()
)

#: VBA functions and objects that stay inside the macro and SolidWorks.
SAFE_BUILTINS = frozenset(
    name.lower()
    for name in """
    Abs Atn Cos Sin Tan Exp Log Sqr Sgn Int Fix Round Rnd Randomize
    CInt CLng CLngLng CDbl CSng CStr CBool CDate CVar CByte CCur CDec Val Str
    Str$ Format Format$ FormatNumber FormatPercent Len Left Left$ Right Right$
    Mid Mid$ InStr InStrRev Replace Split Join Filter Trim Trim$ LTrim LTrim$
    RTrim RTrim$ UCase UCase$ LCase LCase$ Space Space$ String$ StrComp
    StrReverse Chr Chr$ ChrW ChrW$ Asc AscW Hex Hex$ Oct Oct$ IsNumeric
    IsEmpty IsNull IsArray IsObject IsMissing IsDate IsError TypeName VarType
    LBound UBound Array Erase Now Time Time$ Timer DateAdd DateDiff DatePart
    DateSerial DateValue TimeSerial TimeValue Year Month Day Hour Minute
    Second Weekday MsgBox InputBox Err Debug Collection DoEvents IIf Choose
    Switch
    """.split()
)

#: Members of VBA's own objects (``Err``, ``Debug``, ``Collection``).
VBA_OBJECT_MEMBERS = frozenset(
    "number description source clear raise print assert count item add remove".split()
)

#: VBA names that reach outside SolidWorks; named in the refusal.
OUTSIDE = frozenset(
    name.lower()
    for name in """
    Shell CreateObject GetObject CallByName Declare Kill FileCopy MkDir RmDir
    ChDir ChDrive SetAttr GetAttr Environ Environ$ SendKeys AppActivate Open
    Print Write Input Put Get Close Lock Unlock Seek Width Reset Dir Dir$
    FileLen FileDateTime CurDir CurDir$ FreeFile Name Application VBA
    Interaction FileSystem SaveSetting GetSetting GetAllSettings
    DeleteSetting Load Unload Line
    """.split()
)

#: SolidWorks members that touch files, run code, close or quit, or change
#: what persists beyond the documents open now.
BLOCKED_MEMBERS = frozenset(
    name.lower()
    for name in """
    RunMacro RunMacro2 RunAttachedMacro RunCommand RunJournalCmd RunXMLCommand
    RunBatchSaveProcess WriteJournalToMacro WriteToJournalFile JournalManager
    OpenCompFile LoadPointsFromFile LoadModel InsertObject InsertObjectFromFile
    CloseDoc CloseAllDocuments ExitApp Quit QuitDoc CopyDocument RenameDocument
    SetCurrentWorkingDirectory ImportSwSettings LoadAdminSettingsFile
    SetSearchFolders AddSearchFolder RemoveSearchFolder
    LoadAddIn UnloadAddIn GetAddInObject AddIns CallBack AddCallback
    RemoveCallback SetAddinCallbackInfo SetAddinCallbackInfo2
    PrintDirect PrintFile PrintToFile SendDataForNetworkJob
    DownloadFromMySolidWorksSettings UploadToMySolidWorksSettings
    ClickDialogControl SetDialogControlText SetDialogButtonState
    GetCommandManager RemoveAllCommandItems ReplaceCommandItem
    """.split()
)

#: Name prefixes blocked the same way: every member starting with one.
BLOCKED_PREFIXES = (
    "save",
    "export",
    "opendoc",
    "loadfile",
    "closeandreopen",
    "setuserpreference",
    "printout",
    "iprintout",
    "addcommand",
    "removecommand",
    "addtoolbarcommand",
    "createcommandgroup",
)

_TOKEN = re.compile(
    r"(?P<number>&[HhOo][0-9A-Fa-f]+&?|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?[#!@%&]?)"
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_]*[$%&!@]?)"
    r"|(?P<dot>\.)"
    r"|(?P<other>\S)"
)
_DECLARE = re.compile(
    r"^\s*(?:(?:private|public|static|global|dim|redim(?:\s+preserve)?)\b"
    r"(?:\s+(?:dim|const)\b)?|const\b)\s*(?P<rest>.+)$",
    re.I,
)
_PROCEDURE = re.compile(
    r"^\s*(?:(?:private|public|static|friend)\s+)*"
    r"(?:sub|function|property\s+(?:get|let|set))\s+(?P<name>\w+)\s*"
    r"(?:\((?P<params>[^)]*)\))?",
    re.I,
)
_LOOP = re.compile(r"^\s*for\s+(?:each\s+)?(?P<name>\w+)", re.I)
_LABEL = re.compile(r"^\s*(?P<name>[A-Za-z_]\w*):(?:\s|$)")
_BLOCK = re.compile(
    r"^\s*(?:(?:private|public)\s+)?(?P<kind>type|enum)\s+(?P<name>\w+)", re.I
)


def _logical_lines(source: str) -> list[tuple[int, str]]:
    """Source lines with continuations joined, strings and comments removed.

    Returns:
        ``(first physical line number, cleaned text)`` per logical line.
    """
    lines: list[tuple[int, str]] = []
    pending, start = "", 0
    for number, raw in enumerate(source.splitlines(), 1):
        if not pending:
            start = number
        text = pending + raw
        if re.search(r"\s_\s*$", _strip(text)):
            pending = re.sub(r"\s_\s*$", " ", text)
            continue
        pending = ""
        lines.append((start, _strip(text)))
    if pending:
        lines.append((start, _strip(pending)))
    return lines


def _strip(text: str) -> str:
    """Text with quoted strings blanked and any comment removed."""
    out, i, quoted = [], 0, False
    while i < len(text):
        char = text[i]
        if quoted:
            if char == '"' and text[i + 1 : i + 2] == '"':
                i += 2
                continue
            if char == '"':
                quoted = False
                out.append('""')
        elif char == '"':
            quoted = True
        elif char == "'":
            break
        else:
            out.append(char)
        i += 1
    cleaned = "".join(out)
    return re.sub(r"(^|:)\s*rem\b.*$", r"\1", cleaned, flags=re.I)


def _first_name(item: str) -> str | None:
    """The leading identifier of a declaration item, if any."""
    match = re.match(
        r"\s*(?:optional\s+|byval\s+|byref\s+|paramarray\s+)*(\w+)", item, re.I
    )
    return match.group(1).lower() if match else None


def _top_level_items(text: str) -> list[str]:
    """``text`` split on commas that aren't inside parentheses."""
    items: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            items.append("".join(current))
            current = []
            continue
        current.append(char)
    items.append("".join(current))
    return items


def declared_names(lines: Iterable[tuple[int, str]]) -> set[str]:
    """Every name the source declares, lower-cased."""
    names: set[str] = set()
    in_block = False
    for _number, line in lines:
        for statement in line.split(":"):
            if in_block:
                if re.match(r"^\s*end\s+(type|enum)\b", statement, re.I):
                    in_block = False
                elif (name := _first_name(statement)) is not None:
                    names.add(name)
                continue
            if block := _BLOCK.match(statement):
                names.add(block.group("name").lower())
                in_block = True
            elif procedure := _PROCEDURE.match(statement):
                names.add(procedure.group("name").lower())
                for item in _top_level_items(procedure.group("params") or ""):
                    if (name := _first_name(item)) is not None:
                        names.add(name)
            elif declared := _DECLARE.match(statement):
                for item in _top_level_items(declared.group("rest")):
                    if (name := _first_name(item)) is not None:
                        names.add(name)
            elif loop := _LOOP.match(statement):
                names.add(loop.group("name").lower())
        if label := _LABEL.match(line):
            names.add(label.group("name").lower())
    return names


def member_blocked(name: str) -> bool:
    """Whether a SolidWorks member is blocked in restricted mode."""
    lowered = name.lower()
    return lowered in BLOCKED_MEMBERS or lowered.startswith(BLOCKED_PREFIXES)


def check_vba(
    source: str,
    members: Iterable[str],
    constants: Iterable[str],
    interfaces: Iterable[str] = (),
) -> list[str]:
    """Every name in ``source`` that restricted mode refuses, with its line.

    Args:
        source: The macro's VBA text.
        members: Every member name in the SolidWorks type library.
        constants: Every SolidWorks enum and enum value name.
        interfaces: Its interface names; ``IModelDoc2`` allows ``ModelDoc2``
            as a type name.

    Returns:
        list[str]: One ``"line N: <name>: <why>"`` per refusal, in order;
        empty when the source may run.
    """
    lines = _logical_lines(source)
    declared = declared_names(lines)
    known_members = {m.lower() for m in members}
    types = {i.lower().removeprefix("i") for i in interfaces} | {"sldworks"}
    known = KEYWORDS | SAFE_BUILTINS | declared | {c.lower() for c in constants} | types
    refused: list[str] = []

    def _refuse(number: int, name: str, why: str) -> None:
        entry = f"line {number}: {name}: {why}"
        if entry not in refused:
            refused.append(entry)

    for number, line in lines:
        line = re.sub(r"\bproperty\s+(get|let|set)\b", "property", line, flags=re.I)
        tokens = [
            (kind, text)
            for match in _TOKEN.finditer(line)
            for kind, text in match.groupdict().items()
            if text is not None
        ]
        for i, (kind, text) in enumerate(tokens):
            if kind != "name":
                continue
            lowered = text.lower()
            after_dot = i > 0 and tokens[i - 1] == ("dot", ".")
            if after_dot:
                if i >= 2 and tokens[i - 2][1].lower() == "application":
                    continue  # judged with Application
                if member_blocked(text):
                    _refuse(
                        number,
                        text,
                        "a SolidWorks call that reaches outside the open documents",
                    )
                elif (
                    lowered not in known_members | VBA_OBJECT_MEMBERS | declared | types
                ):
                    _refuse(number, text, "not a SolidWorks API member")
                continue
            if lowered == "application":
                follows = tokens[i + 1 : i + 3]
                if [t.lower() for _k, t in follows] == [".", "sldworks"]:
                    continue
                _refuse(number, text, "only Application.SldWorks is allowed")
            elif lowered in declared or lowered in known - OUTSIDE:
                continue
            elif lowered in OUTSIDE:
                _refuse(number, text, "reaches outside SolidWorks")
            elif re.fullmatch(r"vb[a-z]\w*", lowered):
                continue  # a VBA constant such as vbOKCancel
            else:
                _refuse(
                    number,
                    text,
                    "not declared, a safe VBA function or a SolidWorks name; declare it with Dim",
                )
    return refused
