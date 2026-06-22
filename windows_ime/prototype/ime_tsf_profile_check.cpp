#include <fcntl.h>
#include <io.h>
#include <windows.h>
#include <msctf.h>
#include <objbase.h>

#include <iostream>

// {4A5D6F23-A20A-46A4-9CCB-1A7C37D91E30}
const CLSID CLSID_KhmerImeSkeleton = {
    0x4a5d6f23,
    0xa20a,
    0x46a4,
    {0x9c, 0xcb, 0x1a, 0x7c, 0x37, 0xd9, 0x1e, 0x30}
};

// {0DAA9210-9C1B-4A22-B8B8-901FDB753F04}
const GUID GUID_KhmerImeProfile = {
    0x0daa9210,
    0x9c1b,
    0x4a22,
    {0xb8, 0xb8, 0x90, 0x1f, 0xdb, 0x75, 0x3f, 0x04}
};

const LANGID KHMER_CAMBODIA_LANGID = 0x0453;

void print_hresult(const wchar_t* label, HRESULT result)
{
    std::wcout << label << L": 0x" << std::hex << result << std::dec;

    if (SUCCEEDED(result)) {
        std::wcout << L" (OK)";
    }

    std::wcout << L"\n";
}

void print_guid(const GUID& guid)
{
    wchar_t buffer[64] = {};
    StringFromGUID2(guid, buffer, 64);
    std::wcout << buffer;
}

void enumerate_khmer_profiles(ITfInputProcessorProfiles* profiles)
{
    IEnumTfLanguageProfiles* enum_profiles = nullptr;
    HRESULT result = profiles->EnumLanguageProfiles(
        KHMER_CAMBODIA_LANGID,
        &enum_profiles
    );
    print_hresult(L"EnumLanguageProfiles(Khmer)", result);

    if (FAILED(result) || !enum_profiles) {
        return;
    }

    TF_LANGUAGEPROFILE profile = {};
    ULONG fetched = 0;
    int index = 0;

    while (enum_profiles->Next(1, &profile, &fetched) == S_OK && fetched == 1) {
        std::wcout << L"profile[" << index << L"] clsid=";
        print_guid(profile.clsid);
        std::wcout << L" guidProfile=";
        print_guid(profile.guidProfile);
        std::wcout << L" active=" << (profile.fActive ? L"yes" : L"no") << L"\n";
        ++index;
    }

    enum_profiles->Release();
}

int wmain()
{
    _setmode(_fileno(stdout), _O_U16TEXT);

    std::wcout << L"Khmer IME TSF profile check\n";

    HRESULT result = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    print_hresult(L"CoInitializeEx", result);

    if (FAILED(result) && result != RPC_E_CHANGED_MODE) {
        return 1;
    }

    bool should_uninitialize = SUCCEEDED(result);
    ITfInputProcessorProfiles* profiles = nullptr;

    result = CoCreateInstance(
        CLSID_TF_InputProcessorProfiles,
        nullptr,
        CLSCTX_INPROC_SERVER,
        IID_ITfInputProcessorProfiles,
        reinterpret_cast<void**>(&profiles)
    );
    print_hresult(L"CoCreateInstance(CLSID_TF_InputProcessorProfiles)", result);

    if (FAILED(result)) {
        if (should_uninitialize) {
            CoUninitialize();
        }
        return 1;
    }

    BOOL enabled = FALSE;
    result = profiles->IsEnabledLanguageProfile(
        CLSID_KhmerImeSkeleton,
        KHMER_CAMBODIA_LANGID,
        GUID_KhmerImeProfile,
        &enabled
    );
    print_hresult(L"IsEnabledLanguageProfile", result);
    std::wcout << L"enabled: " << (enabled ? L"yes" : L"no") << L"\n";

    BSTR description = nullptr;
    result = profiles->GetLanguageProfileDescription(
        CLSID_KhmerImeSkeleton,
        KHMER_CAMBODIA_LANGID,
        GUID_KhmerImeProfile,
        &description
    );
    print_hresult(L"GetLanguageProfileDescription", result);

    if (description) {
        std::wcout << L"description: " << description << L"\n";
        SysFreeString(description);
    }

    enumerate_khmer_profiles(profiles);

    profiles->Release();

    if (should_uninitialize) {
        CoUninitialize();
    }

    return 0;
}
