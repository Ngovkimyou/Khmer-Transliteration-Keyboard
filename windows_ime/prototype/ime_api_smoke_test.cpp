#include <fcntl.h>
#include <io.h>
#include <windows.h>
#include <winhttp.h>

#include <iostream>
#include <sstream>
#include <string>
#include <vector>

std::wstring utf8_to_wide(const std::string& text)
{
    if (text.empty()) {
        return L"";
    }

    int size = MultiByteToWideChar(
        CP_UTF8,
        0,
        text.data(),
        static_cast<int>(text.size()),
        nullptr,
        0
    );

    if (size <= 0) {
        return L"";
    }

    std::wstring result(size, L'\0');
    MultiByteToWideChar(
        CP_UTF8,
        0,
        text.data(),
        static_cast<int>(text.size()),
        &result[0],
        size
    );

    return result;
}

std::wstring build_suggest_path(const std::wstring& query)
{
    std::wstringstream path;
    path << L"/api/suggest?q=" << query << L"&limit=3";
    return path.str();
}

int wmain(int argc, wchar_t* argv[])
{
    _setmode(_fileno(stdout), _O_U16TEXT);

    std::wstring query = L"somtos";

    if (argc > 1) {
        query = argv[1];
    }

    HINTERNET session = WinHttpOpen(
        L"KhmerImeApiSmokeTest/0.1",
        WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
        WINHTTP_NO_PROXY_NAME,
        WINHTTP_NO_PROXY_BYPASS,
        0
    );

    if (!session) {
        std::wcerr << L"WinHttpOpen failed.\n";
        return 1;
    }

    HINTERNET connection = WinHttpConnect(
        session,
        L"127.0.0.1",
        8000,
        0
    );

    if (!connection) {
        std::wcerr << L"WinHttpConnect failed. Is the local server running?\n";
        WinHttpCloseHandle(session);
        return 1;
    }

    std::wstring path = build_suggest_path(query);
    HINTERNET request = WinHttpOpenRequest(
        connection,
        L"GET",
        path.c_str(),
        nullptr,
        WINHTTP_NO_REFERER,
        WINHTTP_DEFAULT_ACCEPT_TYPES,
        0
    );

    if (!request) {
        std::wcerr << L"WinHttpOpenRequest failed.\n";
        WinHttpCloseHandle(connection);
        WinHttpCloseHandle(session);
        return 1;
    }

    BOOL sent = WinHttpSendRequest(
        request,
        WINHTTP_NO_ADDITIONAL_HEADERS,
        0,
        WINHTTP_NO_REQUEST_DATA,
        0,
        0,
        0
    );

    if (!sent || !WinHttpReceiveResponse(request, nullptr)) {
        std::wcerr << L"Request failed. Is http://127.0.0.1:8000 running?\n";
        WinHttpCloseHandle(request);
        WinHttpCloseHandle(connection);
        WinHttpCloseHandle(session);
        return 1;
    }

    std::string response_body;
    DWORD bytes_available = 0;

    do {
        bytes_available = 0;

        if (!WinHttpQueryDataAvailable(request, &bytes_available)) {
            std::wcerr << L"WinHttpQueryDataAvailable failed.\n";
            break;
        }

        if (bytes_available == 0) {
            break;
        }

        std::vector<char> buffer(bytes_available);
        DWORD bytes_read = 0;

        if (!WinHttpReadData(
                request,
                buffer.data(),
                bytes_available,
                &bytes_read
            )) {
            std::wcerr << L"WinHttpReadData failed.\n";
            break;
        }

        response_body.append(buffer.data(), bytes_read);
    } while (bytes_available > 0);

    WinHttpCloseHandle(request);
    WinHttpCloseHandle(connection);
    WinHttpCloseHandle(session);

    std::wcout << L"Khmer IME API smoke test\n";
    std::wcout << L"query: " << query << L"\n";
    std::wcout << L"response:\n";
    std::wcout << utf8_to_wide(response_body) << L"\n";

    return 0;
}
