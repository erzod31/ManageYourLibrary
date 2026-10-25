"""Windows' built-in local SAPI voice, owned by one opt-in worker thread.

Uses only ctypes/Windows COM; no downloaded reader, service, or new dependency.
Do not instantiate during startup or audio-free tests. All methods, including
close, must be called on the creating thread.
"""
from __future__ import annotations

import ctypes as ct
import sys
import threading
import uuid


class GUID(ct.Structure):
    _fields_ = [('data1', ct.c_uint32), ('data2', ct.c_uint16),
                ('data3', ct.c_uint16), ('data4', ct.c_ubyte * 8)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


class _VariantValue(ct.Union):
    _fields_ = [('integer', ct.c_int32), ('pointer', ct.c_void_p),
                ('record', ct.c_void_p * 2), ('wide', ct.c_int64)]


class VARIANT(ct.Structure):
    _fields_ = [('kind', ct.c_uint16), ('reserved', ct.c_uint16 * 3), ('value', _VariantValue)]


class DISPPARAMS(ct.Structure):
    _fields_ = [('arguments', ct.POINTER(VARIANT)), ('named', ct.POINTER(ct.c_int32)),
                ('count', ct.c_uint32), ('named_count', ct.c_uint32)]


def _check(status):
    if status < 0:
        raise OSError('Local speech COM operation failed (0x%08x)' % (status & 0xffffffff))


class WindowsVoice:
    # Async + purge previous + literal text. Explicitly NOT XML or a filename.
    SPEAK_FLAGS = 1 | 2 | 16

    def __init__(self):
        if sys.platform != 'win32':
            raise OSError('Windows local speech is unavailable on this platform')
        self._owner = threading.get_ident()
        self._dispatch = ct.c_void_p()
        self._initialized = False
        self._ole = ct.WinDLL('ole32')
        self._automation = ct.WinDLL('oleaut32')
        self._ole.CoInitializeEx.argtypes = (ct.c_void_p, ct.c_uint32)
        self._ole.CoInitializeEx.restype = ct.c_int32
        self._ole.CoUninitialize.argtypes = ()
        self._ole.CoUninitialize.restype = None
        self._ole.CLSIDFromProgID.argtypes = (ct.c_wchar_p, ct.POINTER(GUID))
        self._ole.CLSIDFromProgID.restype = ct.c_int32
        self._ole.CoCreateInstance.argtypes = (ct.POINTER(GUID), ct.c_void_p, ct.c_uint32,
                                              ct.POINTER(GUID), ct.POINTER(ct.c_void_p))
        self._ole.CoCreateInstance.restype = ct.c_int32
        self._automation.SysAllocString.argtypes = (ct.c_wchar_p,)
        self._automation.SysAllocString.restype = ct.c_void_p
        self._automation.SysFreeString.argtypes = (ct.c_void_p,)
        self._automation.SysFreeString.restype = None
        try:
            # Dedicated MTA; no COM object crosses a Python/Tk thread boundary.
            _check(self._ole.CoInitializeEx(None, 0))
            self._initialized = True
            clsid = GUID()
            _check(self._ole.CLSIDFromProgID('SAPI.SpVoice', ct.byref(clsid)))
            iid = GUID.parse('00020400-0000-0000-C000-000000000046')
            _check(self._ole.CoCreateInstance(ct.byref(clsid), None, 1, ct.byref(iid), ct.byref(self._dispatch)))
            names = (ct.c_wchar_p * 1)('Speak')
            self._speak_id = ct.c_int32()
            iid_null = GUID()
            get_ids = self._method(5, ct.c_int32, ct.POINTER(GUID), ct.POINTER(ct.c_wchar_p),
                                   ct.c_uint32, ct.c_uint32, ct.POINTER(ct.c_int32))
            _check(get_ids(self._dispatch, ct.byref(iid_null), names, 1, 0, ct.byref(self._speak_id)))
        except Exception:
            self._release()
            raise

    def _method(self, index, result, *arguments):
        table = ct.cast(self._dispatch, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
        return ct.WINFUNCTYPE(result, ct.c_void_p, *arguments)(table[index])

    def _assert_owner(self):
        if threading.get_ident() != self._owner:
            raise RuntimeError('Local speech backend used from another thread')

    def speak(self, text):
        self._assert_owner()
        if not self._dispatch:
            raise RuntimeError('Local speech backend is closed')
        allocated = self._automation.SysAllocString(str(text))
        if not allocated:
            raise MemoryError('Unable to allocate local speech text')
        try:
            arguments = (VARIANT * 2)()
            # IDispatch arguments are in reverse order: flags, then text.
            arguments[0].kind = 3  # VT_I4
            arguments[0].value.integer = self.SPEAK_FLAGS
            arguments[1].kind = 8  # VT_BSTR
            arguments[1].value.pointer = allocated
            parameters = DISPPARAMS(arguments, None, 2, 0)
            iid_null = GUID()
            invoke = self._method(6, ct.c_int32, ct.c_int32, ct.POINTER(GUID), ct.c_uint32,
                                  ct.c_uint16, ct.POINTER(DISPPARAMS), ct.c_void_p, ct.c_void_p, ct.c_void_p)
            _check(invoke(self._dispatch, self._speak_id, ct.byref(iid_null), 0, 1,
                          ct.byref(parameters), None, None, None))
        finally:
            self._automation.SysFreeString(allocated)

    def stop(self):
        self.speak('')  # Purge only this SpVoice instance; no global reader control.

    def _release(self):
        if self._dispatch:
            self._method(2, ct.c_uint32)(self._dispatch)
            self._dispatch = ct.c_void_p()
        if self._initialized:
            self._ole.CoUninitialize()
            self._initialized = False

    def close(self):
        self._assert_owner()
        try:
            if self._dispatch:
                self.stop()
        finally:
            self._release()
