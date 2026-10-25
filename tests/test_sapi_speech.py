"""ABI/COM argument tests using an in-memory fake, with no audio or OS engine."""
import ctypes as ct
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.sapi_speech import DISPPARAMS, GUID, VARIANT, WindowsVoice


class SapiSpeechTests(unittest.TestCase):
    def test_native_layout_and_guid_are_exact(self):
        self.assertEqual(ct.sizeof(GUID), 16)
        self.assertEqual(ct.sizeof(VARIANT), 24 if ct.sizeof(ct.c_void_p) == 8 else 16)
        self.assertEqual(VARIANT.value.offset, 8)
        self.assertEqual(bytes(GUID.parse('00020400-0000-0000-C000-000000000046')),
                         bytes.fromhex('0004020000000000c000000000000046'))

    def fixture(self, status=0):
        voice = object.__new__(WindowsVoice)
        voice._owner = threading.get_ident()
        voice._dispatch = ct.c_void_p(1)
        voice._initialized = True
        voice._speak_id = ct.c_int32(42)
        voice._ole = SimpleNamespace(CoUninitialize=Mock())
        allocated = {}
        def allocate(text):
            buffer = ct.create_unicode_buffer(text)
            pointer = ct.addressof(buffer)
            allocated[pointer] = buffer
            return pointer
        voice._automation = SimpleNamespace(SysAllocString=Mock(side_effect=allocate),
                                            SysFreeString=Mock(side_effect=lambda pointer: allocated.pop(pointer)))
        calls = []
        def invoke(_this, member, _iid, locale, flags, params, result, exception, arg_error):
            values = ct.cast(params, ct.POINTER(DISPPARAMS)).contents
            calls.append((member.value, locale, flags, values.count, values.named_count,
                          values.arguments[0].kind, values.arguments[0].value.integer,
                          values.arguments[1].kind, ct.wstring_at(values.arguments[1].value.pointer),
                          result, exception, arg_error))
            return status
        release = Mock()
        voice._method = Mock(side_effect=lambda index, *_args: invoke if index == 6 else release)
        return voice, calls, allocated, release

    def test_speak_passes_literal_async_text_in_reverse_order_and_frees_bstr(self):
        voice, calls, allocated, _ = self.fixture()
        voice.speak('<book>Árbol</book>')
        self.assertEqual(calls, [(42, 0, 1, 2, 0, 3, 19, 8, '<book>Árbol</book>', None, None, None)])
        self.assertEqual(allocated, {})
        voice._automation.SysFreeString.assert_called_once()

    def test_failed_invoke_still_frees_bstr(self):
        voice, _, allocated, _ = self.fixture(-2147352567)
        with self.assertRaises(OSError):
            voice.speak('Synthetic label')
        self.assertFalse(allocated)

    def test_real_ctypes_vtable_invocation_with_fake_com_object_is_silent(self):
        voice, _, allocated, _ = self.fixture()
        del voice._method  # Exercise the actual function-pointer adapter.
        prototype = getattr(ct, 'WINFUNCTYPE', ct.CFUNCTYPE)
        calls = []
        signature = prototype(ct.c_int32, ct.c_void_p, ct.c_int32, ct.POINTER(GUID),
                              ct.c_uint32, ct.c_uint16, ct.POINTER(DISPPARAMS),
                              ct.c_void_p, ct.c_void_p, ct.c_void_p)
        @signature
        def invoke(_this, member, _iid, _locale, flags, parameters, _result, _exception, _arg_error):
            params = parameters.contents
            calls.append((member, flags, params.count, params.arguments[0].value.integer,
                          ct.wstring_at(params.arguments[1].value.pointer)))
            return 0
        table = (ct.c_void_p * 7)()
        table[6] = ct.cast(invoke, ct.c_void_p)
        class Object(ct.Structure):
            _fields_ = [('vtable', ct.POINTER(ct.c_void_p))]
        instance = Object(table)
        voice._dispatch = ct.cast(ct.pointer(instance), ct.c_void_p)
        with patch.object(ct, 'WINFUNCTYPE', prototype, create=True):
            voice.speak('Synthetic label; no OS voice exists')
        self.assertEqual(calls, [(42, 1, 2, 19, 'Synthetic label; no OS voice exists')])
        self.assertFalse(allocated)

    def test_stop_and_close_purge_only_this_instance_and_release_once(self):
        voice, calls, allocated, release = self.fixture()
        voice.close()
        voice.close()
        self.assertEqual([call[8] for call in calls], [''])
        release.assert_called_once()
        voice._ole.CoUninitialize.assert_called_once()
        self.assertFalse(allocated)
        with self.assertRaises(RuntimeError):
            voice.speak('Closed')

    def test_memory_failure_does_not_invoke_com(self):
        voice, calls, _, _ = self.fixture()
        voice._automation.SysAllocString.side_effect = None
        voice._automation.SysAllocString.return_value = None
        with self.assertRaises(MemoryError):
            voice.speak('Label')
        self.assertFalse(calls)

    def test_cross_thread_call_is_rejected_before_native_calls(self):
        voice, calls, _, _ = self.fixture()
        with patch('core.sapi_speech.threading.get_ident', return_value=voice._owner + 1):
            with self.assertRaises(RuntimeError):
                voice.speak('Wrong thread')
            with self.assertRaises(RuntimeError):
                voice.close()
        self.assertFalse(calls)

    def test_non_windows_import_is_safe_but_constructor_does_not_load_dlls(self):
        with patch('core.sapi_speech.sys.platform', 'linux'):
            with self.assertRaises(OSError):
                WindowsVoice()
