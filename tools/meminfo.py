"""Read-only Windows process memory helpers for reading Sekiro's live state.

Opens the sekiro.exe process with PROCESS_VM_READ only - never writes. Used by
build_flag_map.py for the one-time flag-map calibration.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct

PROCESS_NAME = "sekiro.exe"

kernel32 = ctypes.windll.kernel32
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
TH32CS_SNAPPROCESS = 0x2
TH32CS_SNAPMODULE = 0x8


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)), ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD), ("th32ProcessID", wt.DWORD),
        ("GlblcntUsage", wt.DWORD), ("ProccntUsage", wt.DWORD),
        ("modBaseAddr", ctypes.c_void_p), ("modBaseSize", wt.DWORD),
        ("hModule", ctypes.c_void_p), ("szModule", ctypes.c_wchar * 256),
        ("szExePath", ctypes.c_wchar * 260),
    ]


def find_pid(name: str = PROCESS_NAME) -> int | None:
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    pid = None
    if kernel32.Process32FirstW(snap, ctypes.byref(entry)):
        while True:
            if entry.szExeFile.lower() == name:
                pid = entry.th32ProcessID
                break
            if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                break
    kernel32.CloseHandle(snap)
    return pid


def module_base(pid: int, name: str = PROCESS_NAME) -> tuple[int, int]:
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid)
    entry = MODULEENTRY32W()
    entry.dwSize = ctypes.sizeof(MODULEENTRY32W)
    base = size = 0
    if kernel32.Module32FirstW(snap, ctypes.byref(entry)):
        while True:
            if entry.szModule.lower() == name:
                base, size = entry.modBaseAddr, entry.modBaseSize
                break
            if not kernel32.Module32NextW(snap, ctypes.byref(entry)):
                break
    kernel32.CloseHandle(snap)
    if not base:
        raise RuntimeError("sekiro.exe module not found")
    return base, size


class Mem:
    def __init__(self, pid: int):
        self.h = kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not self.h:
            raise RuntimeError("OpenProcess failed (run as the same user as the game)")

    def read(self, addr: int, size: int) -> bytes | None:
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t()
        ok = kernel32.ReadProcessMemory(
            self.h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got))
        return buf.raw if ok and got.value == size else None

    def u32(self, addr: int) -> int | None:
        b = self.read(addr, 4)
        return None if b is None else struct.unpack("<I", b)[0]

    def u64(self, addr: int) -> int | None:
        b = self.read(addr, 8)
        return None if b is None else struct.unpack("<Q", b)[0]
