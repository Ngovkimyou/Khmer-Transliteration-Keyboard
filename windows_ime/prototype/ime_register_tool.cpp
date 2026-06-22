#include <fcntl.h>
#include <io.h>
#include <windows.h>

#include <iostream>
#include <string>

using RegisterFunction = HRESULT(STDAPICALLTYPE*)();

void print_hresult(const wchar_t* label, HRESULT result)
{
    std::wcout << label << L": 0x" << std::hex << result << std::dec;

    if (SUCCEEDED(result)) {
        std::wcout << L" (OK)";
    }

    std::wcout << L"\n";
}

int wmain(int argc, wchar_t* argv[])
{
    _setmode(_fileno(stdout), _O_U16TEXT);

    if (argc < 3) {
        std::wcerr << L"Usage: ime_register_tool.exe register|unregister path\\to\\ime_tsf_skeleton.dll\n";
        return 2;
    }

    std::wstring command = argv[1];
    const wchar_t* dll_path = argv[2];

    const char* function_name = nullptr;

    if (command == L"register") {
        function_name = "DllRegisterServer";
    } else if (command == L"unregister") {
        function_name = "DllUnregisterServer";
    } else {
        std::wcerr << L"Unknown command: " << command << L"\n";
        return 2;
    }

    HMODULE module = LoadLibraryW(dll_path);

    if (!module) {
        HRESULT result = HRESULT_FROM_WIN32(GetLastError());
        print_hresult(L"LoadLibraryW", result);
        return 1;
    }

    RegisterFunction function = reinterpret_cast<RegisterFunction>(
        GetProcAddress(module, function_name)
    );

    if (!function) {
        HRESULT result = HRESULT_FROM_WIN32(GetLastError());
        print_hresult(L"GetProcAddress", result);
        FreeLibrary(module);
        return 1;
    }

    HRESULT result = function();
    print_hresult(command == L"register" ? L"DllRegisterServer" : L"DllUnregisterServer", result);

    FreeLibrary(module);
    return SUCCEEDED(result) ? 0 : 1;
}
