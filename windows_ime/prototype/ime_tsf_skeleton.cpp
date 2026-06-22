#include <windows.h>
#include <msctf.h>
#include <objbase.h>
#include <winhttp.h>

#include <atomic>
#include <cstdio>
#include <map>
#include <new>
#include <sstream>
#include <string>
#include <vector>

class SkeletonTextService;
LRESULT CALLBACK CandidateWindowProc(HWND window, UINT message, WPARAM wparam, LPARAM lparam);

// Placeholder CLSID for the early COM skeleton.
// This is not registered as a real TSF input method yet.
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
const wchar_t* KHMER_IME_SERVICE_DESCRIPTION = L"Khmer Romanized IME";
const wchar_t* KHMER_ENGINE_PIPE_NAME = L"\\\\.\\pipe\\KhmerRomanizedIme";
const UINT_PTR CANDIDATE_FETCH_TIMER_ID = 1001;
const UINT CANDIDATE_FETCH_COMPLETE_MESSAGE = WM_APP + 41;
const UINT CANDIDATE_FETCH_DEBOUNCE_MS = 120;
const UINT CANDIDATE_FETCH_RETRY_MS = 850;
const int CANDIDATE_FETCH_MAX_RETRIES = 15;
const bool ENABLE_VERBOSE_KEY_EVENT_LOG = false;
const bool ENABLE_VERBOSE_EDIT_LOG = false;

HINSTANCE g_module = nullptr;
std::atomic<long> g_object_count = 0;
std::atomic<long> g_lock_count = 0;

void get_log_path(const wchar_t* file_name, wchar_t* log_path, DWORD log_path_count)
{
    wchar_t module_path[MAX_PATH] = {};

    if (!GetModuleFileNameW(g_module, module_path, MAX_PATH)) {
        wcscpy_s(log_path, log_path_count, file_name);
        return;
    }

    wchar_t* last_slash = wcsrchr(module_path, L'\\');

    if (last_slash) {
        *(last_slash + 1) = L'\0';
        swprintf_s(log_path, log_path_count, L"%s%s", module_path, file_name);
    } else {
        wcscpy_s(log_path, log_path_count, file_name);
    }
}

void write_registration_log(const wchar_t* step, HRESULT result)
{
    if (
        !ENABLE_VERBOSE_EDIT_LOG &&
        (
            wcsncmp(step, L"OnKeyDown", 9) == 0 ||
            wcscmp(step, L"ITfContext::RequestEditSession edit result") == 0 ||
            wcscmp(step, L"ITfRange::SetText") == 0
        )
    ) {
        return;
    }

    wchar_t log_path[MAX_PATH] = {};
    get_log_path(L"ime_tsf_skeleton_register.log", log_path, MAX_PATH);

    FILE* file = nullptr;
    errno_t error = _wfopen_s(&file, log_path, L"a, ccs=UTF-8");

    if (error != 0 || !file) {
        return;
    }

    fwprintf(file, L"%s: 0x%08X%s\n", step, result, SUCCEEDED(result) ? L" (OK)" : L"");
    fclose(file);
}

void clear_registration_log()
{
    wchar_t log_path[MAX_PATH] = {};
    get_log_path(L"ime_tsf_skeleton_register.log", log_path, MAX_PATH);
    DeleteFileW(log_path);
}

void write_key_event_log(const wchar_t* event_name, WPARAM wparam, LPARAM lparam, BOOL foreground = FALSE)
{
    if (
        !ENABLE_VERBOSE_KEY_EVENT_LOG &&
        (
            wcsncmp(event_name, L"OnTestKey", 9) == 0 ||
            wcsncmp(event_name, L"OnKey", 5) == 0 ||
            wcscmp(event_name, L"Candidate popup updated") == 0 ||
            wcscmp(event_name, L"Romanized buffer appended") == 0 ||
            wcscmp(event_name, L"Romanized buffer backspace") == 0 ||
            wcsncmp(event_name, L"request_text_insert", 19) == 0 ||
            wcsncmp(event_name, L"DoEditSession", 13) == 0
        )
    ) {
        return;
    }

    wchar_t log_path[MAX_PATH] = {};
    get_log_path(L"ime_tsf_key_events.log", log_path, MAX_PATH);

    FILE* file = nullptr;
    errno_t error = _wfopen_s(&file, log_path, L"a, ccs=UTF-8");

    if (error != 0 || !file) {
        return;
    }

    fwprintf(
        file,
        L"%s: wParam=0x%04X lParam=0x%08X foreground=%s\n",
        event_name,
        static_cast<unsigned int>(wparam),
        static_cast<unsigned int>(lparam),
        foreground ? L"yes" : L"no"
    );
    fclose(file);
}

void write_key_event_hresult_log(const wchar_t* event_name, HRESULT result)
{
    if (
        !ENABLE_VERBOSE_EDIT_LOG &&
        (
            wcsncmp(event_name, L"ITfContext", 10) == 0 ||
            wcsncmp(event_name, L"ITfRange", 8) == 0 ||
            wcsncmp(event_name, L"ITfComposition", 14) == 0 ||
            wcscmp(event_name, L"QueryInterface(ITfContextComposition)") == 0
        )
    ) {
        return;
    }

    wchar_t log_path[MAX_PATH] = {};
    get_log_path(L"ime_tsf_key_events.log", log_path, MAX_PATH);

    FILE* file = nullptr;
    errno_t error = _wfopen_s(&file, log_path, L"a, ccs=UTF-8");

    if (error != 0 || !file) {
        return;
    }

    fwprintf(file, L"%s: 0x%08X%s\n", event_name, result, SUCCEEDED(result) ? L" (OK)" : L"");
    fclose(file);
}

void write_loaded_module_log()
{
    wchar_t module_path[MAX_PATH] = {};

    if (!GetModuleFileNameW(g_module, module_path, MAX_PATH)) {
        write_key_event_log(L"LoadedModulePathUnavailable", 0, 0);
        return;
    }

    wchar_t log_path[MAX_PATH] = {};
    get_log_path(L"ime_tsf_key_events.log", log_path, MAX_PATH);

    FILE* file = nullptr;
    errno_t error = _wfopen_s(&file, log_path, L"a, ccs=UTF-8");

    if (error != 0 || !file) {
        return;
    }

    fwprintf(file, L"Loaded module: %s\n", module_path);
    fclose(file);
}

bool is_alpha_key(WPARAM wparam)
{
    return wparam >= L'A' && wparam <= L'Z';
}

bool is_commit_key(WPARAM wparam)
{
    return wparam == VK_RETURN;
}

bool is_buffer_control_key(WPARAM wparam)
{
    return wparam == VK_BACK || wparam == VK_ESCAPE || wparam == VK_SPACE;
}

wchar_t key_to_buffer_char(WPARAM wparam)
{
    if (wparam >= L'A' && wparam <= L'Z') {
        return static_cast<wchar_t>(L'a' + (wparam - L'A'));
    }

    if (wparam == VK_SPACE) {
        return L' ';
    }

    return L'\0';
}

std::string wide_to_utf8(const std::wstring& text)
{
    if (text.empty()) {
        return "";
    }

    int size = WideCharToMultiByte(
        CP_UTF8,
        0,
        text.data(),
        static_cast<int>(text.size()),
        nullptr,
        0,
        nullptr,
        nullptr
    );

    if (size <= 0) {
        return "";
    }

    std::string result(size, '\0');
    WideCharToMultiByte(
        CP_UTF8,
        0,
        text.data(),
        static_cast<int>(text.size()),
        &result[0],
        size,
        nullptr,
        nullptr
    );

    return result;
}

std::wstring url_encode_ascii(const std::wstring& text)
{
    std::wstringstream encoded;

    for (wchar_t character : text) {
        if (
            (character >= L'a' && character <= L'z') ||
            (character >= L'A' && character <= L'Z') ||
            (character >= L'0' && character <= L'9') ||
            character == L'-' ||
            character == L'_' ||
            character == L'.'
        ) {
            encoded << character;
        } else if (character == L' ') {
            encoded << L"%20";
        }
    }

    return encoded.str();
}

std::wstring json_hex_to_wide(const std::string& hex)
{
    wchar_t* end = nullptr;
    unsigned long code = wcstoul(std::wstring(hex.begin(), hex.end()).c_str(), &end, 16);
    return std::wstring(1, static_cast<wchar_t>(code));
}

std::wstring parse_json_string_value(const std::string& json, size_t value_start)
{
    std::wstring value;
    std::string utf8_chunk;

    auto flush_utf8_chunk = [&]() {
        if (utf8_chunk.empty()) {
            return;
        }

        int size = MultiByteToWideChar(
            CP_UTF8,
            0,
            utf8_chunk.data(),
            static_cast<int>(utf8_chunk.size()),
            nullptr,
            0
        );

        if (size > 0) {
            std::wstring wide_chunk(size, L'\0');
            MultiByteToWideChar(
                CP_UTF8,
                0,
                utf8_chunk.data(),
                static_cast<int>(utf8_chunk.size()),
                &wide_chunk[0],
                size
            );
            value += wide_chunk;
        }

        utf8_chunk.clear();
    };

    for (size_t index = value_start; index < json.size(); ++index) {
        char character = json[index];

        if (character == '"') {
            break;
        }

        if (character == '\\' && index + 1 < json.size()) {
            char escaped = json[++index];
            flush_utf8_chunk();

            if (escaped == 'u' && index + 4 < json.size()) {
                value += json_hex_to_wide(json.substr(index + 1, 4));
                index += 4;
            } else if (escaped == '"' || escaped == '\\' || escaped == '/') {
                value += static_cast<wchar_t>(escaped);
            } else if (escaped == 'n') {
                value += L'\n';
            }

            continue;
        }

        utf8_chunk += character;
    }

    flush_utf8_chunk();
    return value;
}

std::vector<std::wstring> extract_khmer_suggestions_from_response(const std::string& response_body)
{
    const std::string key = "\"khmer\"";
    std::vector<std::wstring> suggestions;
    size_t search_position = 0;

    while (suggestions.size() < 20) {
        size_t key_position = response_body.find(key, search_position);

        if (key_position == std::string::npos) {
            break;
        }

        size_t colon_position = response_body.find(':', key_position + key.size());

        if (colon_position == std::string::npos) {
            break;
        }

        size_t quote_position = response_body.find('"', colon_position + 1);

        if (quote_position == std::string::npos) {
            break;
        }

        suggestions.push_back(parse_json_string_value(response_body, quote_position + 1));
        search_position = quote_position + 1;
    }

    return suggestions;
}

std::wstring parent_directory(const std::wstring& path)
{
    size_t slash = path.find_last_of(L"\\/");

    if (slash == std::wstring::npos) {
        return L"";
    }

    return path.substr(0, slash);
}

std::wstring suggestion_cache_key(const std::wstring& buffer, const std::wstring& previous_word)
{
    return previous_word + L"\x1F" + buffer;
}

std::wstring find_pipe_engine_launcher()
{
    wchar_t module_path[MAX_PATH] = {};

    if (!GetModuleFileNameW(g_module, module_path, MAX_PATH)) {
        write_key_event_hresult_log(L"Pipe launcher GetModuleFileNameW", HRESULT_FROM_WIN32(GetLastError()));
        return L"";
    }

    std::wstring build_dir = parent_directory(module_path);
    std::wstring prototype_dir = parent_directory(build_dir);
    std::wstring windows_ime_dir = parent_directory(prototype_dir);

    if (windows_ime_dir.empty()) {
        write_key_event_hresult_log(L"Pipe launcher path resolve", HRESULT_FROM_WIN32(ERROR_BAD_PATHNAME));
        return L"";
    }

    std::wstring launcher = windows_ime_dir + L"\\engine\\start_pipe_engine.cmd";
    DWORD attributes = GetFileAttributesW(launcher.c_str());

    if (attributes == INVALID_FILE_ATTRIBUTES || (attributes & FILE_ATTRIBUTE_DIRECTORY)) {
        write_key_event_hresult_log(L"Pipe launcher missing", HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND));
        return L"";
    }

    return launcher;
}

bool try_start_pipe_engine()
{
    static ULONGLONG last_attempt_tick = 0;
    ULONGLONG now = GetTickCount64();

    if (last_attempt_tick != 0 && now - last_attempt_tick < 10000) {
        return false;
    }

    last_attempt_tick = now;

    std::wstring launcher = find_pipe_engine_launcher();

    if (launcher.empty()) {
        return false;
    }

    wchar_t command_processor[MAX_PATH] = {};
    DWORD command_processor_length = GetEnvironmentVariableW(
        L"ComSpec",
        command_processor,
        MAX_PATH
    );

    std::wstring command_exe = command_processor_length > 0
        ? std::wstring(command_processor)
        : L"C:\\Windows\\System32\\cmd.exe";
    std::wstring command_line = L"\"" + command_exe + L"\" /c \"" + launcher + L"\"";
    std::wstring working_directory = parent_directory(parent_directory(launcher));

    STARTUPINFOW startup_info = {};
    startup_info.cb = sizeof(startup_info);
    startup_info.dwFlags = STARTF_USESHOWWINDOW;
    startup_info.wShowWindow = SW_HIDE;

    PROCESS_INFORMATION process_info = {};
    BOOL started = CreateProcessW(
        nullptr,
        &command_line[0],
        nullptr,
        nullptr,
        FALSE,
        CREATE_NO_WINDOW,
        nullptr,
        working_directory.empty() ? nullptr : working_directory.c_str(),
        &startup_info,
        &process_info
    );

    if (!started) {
        write_key_event_hresult_log(L"Pipe engine CreateProcessW", HRESULT_FROM_WIN32(GetLastError()));
        return false;
    }

    CloseHandle(process_info.hThread);
    CloseHandle(process_info.hProcess);
    write_key_event_log(L"Pipe engine launch requested", 0, 0);
    return true;
}

std::string json_escape_utf8(const std::wstring& text)
{
    std::string query = wide_to_utf8(text);
    std::string escaped_query;

    for (char character : query) {
        if (character == '"' || character == '\\') {
            escaped_query += '\\';
        }

        escaped_query += character;
    }

    return escaped_query;
}

std::string build_pipe_suggestion_request(
    const std::wstring& romanized_buffer,
    int limit,
    const std::wstring& previous_word = L""
)
{
    std::string request = "{\"q\":\"";
    request += json_escape_utf8(romanized_buffer);
    request += "\",\"limit\":";
    request += std::to_string(limit);
    request += ",\"previous_word\":\"";
    request += json_escape_utf8(previous_word);
    request += "\"";
    request += "}\n";
    return request;
}

std::string build_pipe_selection_request(
    const std::wstring& romanized_buffer,
    const std::wstring& khmer,
    const std::wstring& previous_word
)
{
    std::string request = "{\"action\":\"select\",\"q\":\"";
    request += json_escape_utf8(romanized_buffer);
    request += "\",\"khmer\":\"";
    request += json_escape_utf8(khmer);
    request += "\",\"previous_word\":\"";
    request += json_escape_utf8(previous_word);
    request += "\"}\n";
    return request;
}

std::string send_pipe_request(const std::string& request_body)
{
    if (!WaitNamedPipeW(KHMER_ENGINE_PIPE_NAME, 40)) {
        DWORD wait_error = GetLastError();
        write_key_event_hresult_log(L"Pipe WaitNamedPipeW", HRESULT_FROM_WIN32(wait_error));

        if (!try_start_pipe_engine()) {
            return "";
        }

        if (!WaitNamedPipeW(KHMER_ENGINE_PIPE_NAME, 1200)) {
            write_key_event_hresult_log(L"Pipe WaitNamedPipeW after launch", HRESULT_FROM_WIN32(GetLastError()));
            return "";
        }
    }

    HANDLE pipe = CreateFileW(
        KHMER_ENGINE_PIPE_NAME,
        GENERIC_READ | GENERIC_WRITE,
        0,
        nullptr,
        OPEN_EXISTING,
        0,
        nullptr
    );

    if (pipe == INVALID_HANDLE_VALUE) {
        write_key_event_hresult_log(L"Pipe CreateFileW", HRESULT_FROM_WIN32(GetLastError()));
        return "";
    }

    DWORD bytes_written = 0;
    BOOL wrote = WriteFile(
        pipe,
        request_body.data(),
        static_cast<DWORD>(request_body.size()),
        &bytes_written,
        nullptr
    );

    if (!wrote) {
        write_key_event_hresult_log(L"Pipe WriteFile", HRESULT_FROM_WIN32(GetLastError()));
        CloseHandle(pipe);
        return "";
    }

    std::string response_body;
    char buffer[4096] = {};

    while (true) {
        DWORD bytes_read = 0;
        BOOL read = ReadFile(pipe, buffer, sizeof(buffer), &bytes_read, nullptr);

        if (!read) {
            DWORD error = GetLastError();

            if (error != ERROR_BROKEN_PIPE) {
                write_key_event_hresult_log(L"Pipe ReadFile", HRESULT_FROM_WIN32(error));
            }

            break;
        }

        if (bytes_read == 0) {
            break;
        }

        response_body.append(buffer, bytes_read);

        if (response_body.find('\n') != std::string::npos) {
            break;
        }
    }

    CloseHandle(pipe);
    return response_body;
}

std::vector<std::wstring> fetch_khmer_suggestions_from_pipe(
    const std::wstring& romanized_buffer,
    int limit,
    const std::wstring& previous_word = L""
)
{
    std::string response_body = send_pipe_request(
        build_pipe_suggestion_request(romanized_buffer, limit, previous_word)
    );
    std::vector<std::wstring> suggestions = extract_khmer_suggestions_from_response(response_body);
    write_key_event_log(suggestions.empty() ? L"Pipe suggestions empty" : L"Pipe suggestions found", 0, 0);
    return suggestions;
}

void record_khmer_selection(
    const std::wstring& romanized_buffer,
    const std::wstring& khmer,
    const std::wstring& previous_word
)
{
    send_pipe_request(build_pipe_selection_request(romanized_buffer, khmer, previous_word));
}

struct SelectionRecordRequest
{
    std::wstring buffer;
    std::wstring khmer;
    std::wstring previous_word;
};

DWORD WINAPI SelectionRecordThreadProc(LPVOID parameter)
{
    SelectionRecordRequest* request = reinterpret_cast<SelectionRecordRequest*>(parameter);

    if (!request) {
        return 0;
    }

    record_khmer_selection(request->buffer, request->khmer, request->previous_word);
    delete request;
    return 0;
}

void record_khmer_selection_async(
    const std::wstring& romanized_buffer,
    const std::wstring& khmer,
    const std::wstring& previous_word
)
{
    SelectionRecordRequest* request = new (std::nothrow) SelectionRecordRequest();

    if (!request) {
        return;
    }

    request->buffer = romanized_buffer;
    request->khmer = khmer;
    request->previous_word = previous_word;

    HANDLE thread = CreateThread(
        nullptr,
        0,
        SelectionRecordThreadProc,
        request,
        0,
        nullptr
    );

    if (!thread) {
        delete request;
        return;
    }

    CloseHandle(thread);
}

std::vector<std::wstring> fetch_khmer_suggestions_from_http(const std::wstring& romanized_buffer, int limit)
{
    HINTERNET session = WinHttpOpen(
        L"KhmerImePrototype/0.1",
        WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
        WINHTTP_NO_PROXY_NAME,
        WINHTTP_NO_PROXY_BYPASS,
        0
    );

    if (!session) {
        write_key_event_hresult_log(L"WinHttpOpen", HRESULT_FROM_WIN32(GetLastError()));
        return {};
    }

    WinHttpSetTimeouts(session, 200, 300, 300, 600);

    HINTERNET connection = WinHttpConnect(session, L"127.0.0.1", 8000, 0);

    if (!connection) {
        write_key_event_hresult_log(L"WinHttpConnect", HRESULT_FROM_WIN32(GetLastError()));
        WinHttpCloseHandle(session);
        return {};
    }

    std::wstringstream path_stream;
    path_stream << L"/api/suggest?q=" << url_encode_ascii(romanized_buffer)
                << L"&limit=" << limit;
    std::wstring path = path_stream.str();
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
        write_key_event_hresult_log(L"WinHttpOpenRequest", HRESULT_FROM_WIN32(GetLastError()));
        WinHttpCloseHandle(connection);
        WinHttpCloseHandle(session);
        return {};
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
        write_key_event_hresult_log(L"WinHttp request", HRESULT_FROM_WIN32(GetLastError()));
        WinHttpCloseHandle(request);
        WinHttpCloseHandle(connection);
        WinHttpCloseHandle(session);
        return {};
    }

    std::string response_body;
    DWORD bytes_available = 0;

    do {
        bytes_available = 0;

        if (!WinHttpQueryDataAvailable(request, &bytes_available)) {
            break;
        }

        if (bytes_available == 0) {
            break;
        }

        std::vector<char> buffer(bytes_available);
        DWORD bytes_read = 0;

        if (!WinHttpReadData(request, buffer.data(), bytes_available, &bytes_read)) {
            break;
        }

        response_body.append(buffer.data(), bytes_read);
    } while (bytes_available > 0);

    WinHttpCloseHandle(request);
    WinHttpCloseHandle(connection);
    WinHttpCloseHandle(session);

    std::vector<std::wstring> suggestions = extract_khmer_suggestions_from_response(response_body);
    write_key_event_log(suggestions.empty() ? L"API suggestions empty" : L"API suggestions found", 0, 0);
    return suggestions;
}

std::vector<std::wstring> fetch_khmer_suggestions(
    const std::wstring& romanized_buffer,
    int limit = 5,
    const std::wstring& previous_word = L""
)
{
    return fetch_khmer_suggestions_from_pipe(romanized_buffer, limit, previous_word);
}

struct CandidateFetchRequest
{
    HWND window;
    std::wstring buffer;
    std::wstring previous_word;
    std::wstring cache_key;
    int limit;
};

struct CandidateFetchResult
{
    std::wstring buffer;
    std::wstring previous_word;
    std::wstring cache_key;
    std::vector<std::wstring> suggestions;
};

DWORD WINAPI CandidateFetchThreadProc(LPVOID parameter)
{
    CandidateFetchRequest* request = reinterpret_cast<CandidateFetchRequest*>(parameter);

    if (!request) {
        return 0;
    }

    CandidateFetchResult* result = new (std::nothrow) CandidateFetchResult();

    if (!result) {
        delete request;
        return 0;
    }

    HWND window = request->window;
    result->buffer = request->buffer;
    result->previous_word = request->previous_word;
    result->cache_key = request->cache_key;
    result->suggestions = fetch_khmer_suggestions(
        request->buffer,
        request->limit,
        request->previous_word
    );
    delete request;

    if (!PostMessageW(
        window,
        CANDIDATE_FETCH_COMPLETE_MESSAGE,
        0,
        reinterpret_cast<LPARAM>(result)
    )) {
        delete result;
    }

    return 0;
}

std::wstring format_candidate_text(const std::vector<std::wstring>& candidates)
{
    std::wstring text;

    for (size_t index = 0; index < candidates.size(); ++index) {
        if (!text.empty()) {
            text += L"    ";
        }

        text += std::to_wstring(index + 1);
        text += L" ";
        text += candidates[index];
    }

    return text;
}

size_t candidate_page_start_for_selection(size_t selected_index)
{
    return selected_index < 5 ? 0 : (selected_index / 10) * 10;
}

std::wstring format_vertical_candidate_text(
    const std::wstring& romanized_buffer,
    const std::vector<std::wstring>& candidates,
    size_t selected_index
)
{
    UNREFERENCED_PARAMETER(romanized_buffer);
    size_t visible_count = selected_index < 5 ? 5 : 10;
    size_t page_start = candidate_page_start_for_selection(selected_index);
    size_t page_end = min(candidates.size(), page_start + visible_count);
    std::wstring text;

    if (page_start > 0) {
        text += L"^ more above\r\n";
    }

    for (size_t index = page_start; index < page_end; ++index) {
        text += index == selected_index ? L"> " : L"  ";
        size_t local_number = index - page_start + 1;
        text += std::to_wstring(local_number);
        text += L"  ";
        text += candidates[index];
        text += L"\r\n";
    }

    if (page_end < candidates.size()) {
        text += L"v more below";
    }

    return text;
}

size_t visible_candidate_count_for_selection(size_t selected_index)
{
    return selected_index < 5 ? 5 : 10;
}

int candidate_row_height()
{
    return 44;
}

int candidate_padding()
{
    return 10;
}

int candidate_gutter_width()
{
    return 28;
}

POINT get_candidate_anchor_point()
{
    GUITHREADINFO gui_info = {};
    gui_info.cbSize = sizeof(GUITHREADINFO);
    DWORD thread_id = GetWindowThreadProcessId(GetForegroundWindow(), nullptr);

    if (GetGUIThreadInfo(thread_id, &gui_info) && gui_info.hwndCaret) {
        POINT caret_point = {
            gui_info.rcCaret.left,
            gui_info.rcCaret.bottom
        };

        if (ClientToScreen(gui_info.hwndCaret, &caret_point)) {
            return caret_point;
        }
    }

    POINT cursor = {};
    GetCursorPos(&cursor);
    return cursor;
}

void position_candidate_window(HWND window, int width, int height)
{
    const int margin = 8;
    POINT anchor = get_candidate_anchor_point();
    HMONITOR monitor = MonitorFromPoint(anchor, MONITOR_DEFAULTTONEAREST);
    MONITORINFO monitor_info = {};
    monitor_info.cbSize = sizeof(MONITORINFO);
    GetMonitorInfoW(monitor, &monitor_info);

    RECT work_area = monitor_info.rcWork;
    int x = anchor.x;
    int y = anchor.y + margin;
    int space_below = work_area.bottom - anchor.y;
    int space_above = anchor.y - work_area.top;

    if (space_below < height + margin && space_above > space_below) {
        y = anchor.y - height - margin;
    }

    if (x + width > work_area.right - margin) {
        x = work_area.right - width - margin;
    }

    if (x < work_area.left + margin) {
        x = work_area.left + margin;
    }

    if (y < work_area.top + margin) {
        y = work_area.top + margin;
    }

    if (y + height > work_area.bottom - margin) {
        y = work_area.bottom - height - margin;
    }

    SetWindowPos(
        window,
        HWND_TOPMOST,
        x,
        y,
        width,
        height,
        SWP_NOACTIVATE | SWP_SHOWWINDOW
    );

    HRGN rounded_region = CreateRoundRectRgn(0, 0, width + 1, height + 1, 18, 18);

    if (rounded_region) {
        SetWindowRgn(window, rounded_region, TRUE);
    }
}

class InsertTextEditSession : public ITfEditSession
{
public:
    InsertTextEditSession(
        ITfContext* context,
        const std::wstring& text,
        LONG replace_previous_count = 0,
        ITfCompositionSink* composition_sink = nullptr,
        ITfComposition** composition = nullptr,
        bool update_composition = false,
        bool end_composition = false
    )
        : ref_count_(1)
        , context_(context)
        , text_(text)
        , replace_previous_count_(replace_previous_count)
        , composition_sink_(composition_sink)
        , composition_(composition)
        , update_composition_(update_composition)
        , end_composition_(end_composition)
    {
        if (context_) {
            context_->AddRef();
        }

        if (composition_sink_) {
            composition_sink_->AddRef();
        }
    }

    ~InsertTextEditSession()
    {
        if (context_) {
            context_->Release();
        }

        if (composition_sink_) {
            composition_sink_->Release();
        }
    }

    STDMETHODIMP QueryInterface(REFIID riid, void** object) override
    {
        if (!object) {
            return E_POINTER;
        }

        *object = nullptr;

        if (riid == IID_IUnknown || riid == IID_ITfEditSession) {
            *object = static_cast<ITfEditSession*>(this);
            AddRef();
            return S_OK;
        }

        return E_NOINTERFACE;
    }

    STDMETHODIMP_(ULONG) AddRef() override
    {
        return InterlockedIncrement(&ref_count_);
    }

    STDMETHODIMP_(ULONG) Release() override
    {
        ULONG ref_count = InterlockedDecrement(&ref_count_);

        if (ref_count == 0) {
            delete this;
        }

        return ref_count;
    }

    STDMETHODIMP DoEditSession(TfEditCookie edit_cookie) override
    {
        write_key_event_log(L"DoEditSession entered", 0, 0);

        if (!context_) {
            write_key_event_log(L"DoEditSession missing context", 0, 0);
            return E_FAIL;
        }

        TF_SELECTION selection = {};
        ULONG fetched = 0;

        HRESULT result = context_->GetSelection(
            edit_cookie,
            TF_DEFAULT_SELECTION,
            1,
            &selection,
            &fetched
        );
        write_key_event_hresult_log(L"ITfContext::GetSelection", result);

        if (FAILED(result) || fetched == 0 || !selection.range) {
            write_key_event_log(L"DoEditSession no selection range", 0, 0);
            return result;
        }

        if (replace_previous_count_ > 0) {
            LONG shifted = 0;
            result = selection.range->ShiftStart(
                edit_cookie,
                -replace_previous_count_,
                &shifted,
                nullptr
            );
            write_key_event_hresult_log(L"ITfRange::ShiftStart", result);

            if (FAILED(result)) {
                selection.range->Release();
                return result;
            }
        }

        write_key_event_log(L"DoEditSession before SetText", 0, 0);
        result = selection.range->SetText(
            edit_cookie,
            0,
            text_.c_str(),
            static_cast<LONG>(text_.size())
        );
        write_key_event_hresult_log(L"ITfRange::SetText", result);
        write_registration_log(L"ITfRange::SetText", result);

        if (SUCCEEDED(result)) {
            if (update_composition_ && composition_ && !*composition_ && composition_sink_) {
                ITfContextComposition* context_composition = nullptr;
                HRESULT composition_result = context_->QueryInterface(
                    IID_ITfContextComposition,
                    reinterpret_cast<void**>(&context_composition)
                );
                write_key_event_hresult_log(L"QueryInterface(ITfContextComposition)", composition_result);

                if (SUCCEEDED(composition_result)) {
                    composition_result = context_composition->StartComposition(
                        edit_cookie,
                        selection.range,
                        composition_sink_,
                        composition_
                    );
                    write_key_event_hresult_log(L"ITfContextComposition::StartComposition", composition_result);
                    context_composition->Release();
                }
            }

            if (end_composition_ && composition_ && *composition_) {
                HRESULT end_result = (*composition_)->EndComposition(edit_cookie);
                write_key_event_hresult_log(L"ITfComposition::EndComposition", end_result);
                (*composition_)->Release();
                *composition_ = nullptr;
            }

            HRESULT collapse_result = selection.range->Collapse(edit_cookie, TF_ANCHOR_END);
            write_key_event_hresult_log(L"ITfRange::Collapse(end)", collapse_result);

            if (SUCCEEDED(collapse_result)) {
                selection.style.ase = TF_AE_END;
                selection.style.fInterimChar = FALSE;
                HRESULT selection_result = context_->SetSelection(edit_cookie, 1, &selection);
                write_key_event_hresult_log(L"ITfContext::SetSelection(end)", selection_result);
            }
        }

        selection.range->Release();
        return result;
    }

private:
    long ref_count_;
    ITfContext* context_;
    std::wstring text_;
    LONG replace_previous_count_;
    ITfCompositionSink* composition_sink_;
    ITfComposition** composition_;
    bool update_composition_;
    bool end_composition_;
};

class SkeletonTextService : public ITfTextInputProcessor, public ITfKeyEventSink, public ITfCompositionSink
{
public:
    SkeletonTextService()
        : ref_count_(1)
        , thread_manager_(nullptr)
        , keystroke_manager_(nullptr)
        , client_id_(TF_CLIENTID_NULL)
        , romanized_buffer_()
        , candidate_window_(nullptr)
        , candidate_font_(nullptr)
        , candidates_()
        , selected_candidate_index_(0)
        , hover_candidate_index_(static_cast<size_t>(-1))
        , suggestion_cache_()
        , pending_fetch_buffer_()
        , candidate_fetch_retry_count_(0)
        , candidate_fetch_in_progress_(false)
        , previous_committed_khmer_()
        , last_context_(nullptr)
        , composition_(nullptr)
    {
        ++g_object_count;
    }

    ~SkeletonTextService()
    {
        if (thread_manager_) {
            thread_manager_->Release();
        }

        if (keystroke_manager_) {
            keystroke_manager_->Release();
        }

        if (last_context_) {
            last_context_->Release();
            last_context_ = nullptr;
        }

        if (composition_) {
            composition_->Release();
            composition_ = nullptr;
        }

        hide_candidate_window();

        if (candidate_font_) {
            DeleteObject(candidate_font_);
            candidate_font_ = nullptr;
        }

        --g_object_count;
    }

    STDMETHODIMP QueryInterface(REFIID riid, void** object) override
    {
        if (!object) {
            return E_POINTER;
        }

        *object = nullptr;

        if (riid == IID_IUnknown || riid == IID_ITfTextInputProcessor) {
            *object = static_cast<ITfTextInputProcessor*>(this);
            AddRef();
            return S_OK;
        }

        if (riid == IID_ITfKeyEventSink) {
            *object = static_cast<ITfKeyEventSink*>(this);
            AddRef();
            return S_OK;
        }

        if (riid == IID_ITfCompositionSink) {
            *object = static_cast<ITfCompositionSink*>(this);
            AddRef();
            return S_OK;
        }

        return E_NOINTERFACE;
    }

    STDMETHODIMP_(ULONG) AddRef() override
    {
        return InterlockedIncrement(&ref_count_);
    }

    STDMETHODIMP_(ULONG) Release() override
    {
        ULONG ref_count = InterlockedDecrement(&ref_count_);

        if (ref_count == 0) {
            delete this;
        }

        return ref_count;
    }

    STDMETHODIMP Activate(ITfThreadMgr* thread_manager, TfClientId client_id) override
    {
        write_loaded_module_log();
        write_key_event_log(L"Activate", 0, 0, TRUE);

        if (thread_manager_) {
            thread_manager_->Release();
            thread_manager_ = nullptr;
        }

        if (keystroke_manager_) {
            keystroke_manager_->UnadviseKeyEventSink(client_id_);
            keystroke_manager_->Release();
            keystroke_manager_ = nullptr;
        }

        thread_manager_ = thread_manager;

        if (thread_manager_) {
            thread_manager_->AddRef();
        }

        client_id_ = client_id;
        HRESULT result = E_FAIL;

        if (thread_manager_) {
            result = thread_manager_->QueryInterface(
                IID_ITfKeystrokeMgr,
                reinterpret_cast<void**>(&keystroke_manager_)
            );
        }

        if (SUCCEEDED(result) && keystroke_manager_) {
            result = keystroke_manager_->AdviseKeyEventSink(client_id_, this, TRUE);
        }

        write_registration_log(L"ITfKeystrokeMgr::AdviseKeyEventSink", result);
        return S_OK;
    }

    STDMETHODIMP Deactivate() override
    {
        write_key_event_log(L"Deactivate", 0, 0, FALSE);

        if (keystroke_manager_) {
            keystroke_manager_->UnadviseKeyEventSink(client_id_);
            keystroke_manager_->Release();
            keystroke_manager_ = nullptr;
        }

        if (thread_manager_) {
            thread_manager_->Release();
            thread_manager_ = nullptr;
        }

        client_id_ = TF_CLIENTID_NULL;
        romanized_buffer_.clear();
        candidates_.clear();
        pending_fetch_buffer_.clear();
        candidate_fetch_retry_count_ = 0;
        selected_candidate_index_ = 0;
        hover_candidate_index_ = static_cast<size_t>(-1);
        if (last_context_) {
            last_context_->Release();
            last_context_ = nullptr;
        }
        if (composition_) {
            composition_->Release();
            composition_ = nullptr;
        }
        hide_candidate_window();
        return S_OK;
    }

    STDMETHODIMP OnSetFocus(BOOL foreground) override
    {
        write_key_event_log(L"OnSetFocus", 0, 0, foreground);
        return S_OK;
    }

    STDMETHODIMP OnCompositionTerminated(TfEditCookie, ITfComposition*) override
    {
        write_key_event_log(L"OnCompositionTerminated", 0, 0);

        if (composition_) {
            composition_->Release();
            composition_ = nullptr;
        }

        romanized_buffer_.clear();
        candidates_.clear();
        pending_fetch_buffer_.clear();
        candidate_fetch_retry_count_ = 0;
        selected_candidate_index_ = 0;
        hide_candidate_window();
        return S_OK;
    }

    void request_text_insert(ITfContext* context, const std::wstring& text, const wchar_t* log_label)
    {
        request_text_replace(context, text, 0, log_label);
    }

    void request_text_replace(
        ITfContext* context,
        const std::wstring& text,
        LONG replace_previous_count,
        const wchar_t* log_label,
        bool update_composition = false,
        bool end_composition = false
    )
    {
        write_key_event_log(L"request_text_insert entered", 0, 0);

        if (!context) {
            write_key_event_log(L"request_text_insert missing context", 0, 0);
            write_registration_log(log_label, E_POINTER);
            return;
        }

        write_key_event_log(L"request_text_insert has context", 0, 0);

        InsertTextEditSession* edit_session = new (std::nothrow) InsertTextEditSession(
            context,
            text,
            replace_previous_count,
            static_cast<ITfCompositionSink*>(this),
            &composition_,
            update_composition,
            end_composition
        );

        if (!edit_session) {
            write_key_event_log(L"request_text_insert allocation failed", 0, 0);
            write_registration_log(log_label, E_OUTOFMEMORY);
            return;
        }

        HRESULT edit_session_result = E_FAIL;
        HRESULT request_result = context->RequestEditSession(
            client_id_,
            edit_session,
            TF_ES_ASYNC | TF_ES_READWRITE,
            &edit_session_result
        );
        write_key_event_log(L"request_text_insert requested edit session", 0, 0);
        write_registration_log(log_label, request_result);
        write_registration_log(L"ITfContext::RequestEditSession edit result", edit_session_result);

        if (request_result != TF_S_ASYNC) {
            edit_session->Release();
        }
    }

    void remember_context(ITfContext* context)
    {
        if (!context || context == last_context_) {
            return;
        }

        context->AddRef();

        if (last_context_) {
            last_context_->Release();
        }

        last_context_ = context;
    }

    void ensure_candidate_window()
    {
        if (candidate_window_) {
            return;
        }

        static bool registered_candidate_class = false;

        if (!registered_candidate_class) {
            WNDCLASSW window_class = {};
            window_class.lpfnWndProc = CandidateWindowProc;
            window_class.hInstance = g_module;
            window_class.lpszClassName = L"KhmerImeCandidateWindow";
            window_class.hbrBackground = nullptr;
            window_class.hCursor = LoadCursorW(nullptr, MAKEINTRESOURCEW(32512));
            RegisterClassW(&window_class);
            registered_candidate_class = true;
        }

        candidate_window_ = CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            L"KhmerImeCandidateWindow",
            L"",
            WS_POPUP,
            0,
            0,
            100,
            32,
            nullptr,
            nullptr,
            g_module,
            this
        );

        if (!candidate_font_) {
            candidate_font_ = CreateFontW(
                30,
                0,
                0,
                0,
                FW_NORMAL,
                FALSE,
                FALSE,
                FALSE,
                DEFAULT_CHARSET,
                OUT_DEFAULT_PRECIS,
                CLIP_DEFAULT_PRECIS,
                CLEARTYPE_QUALITY,
                DEFAULT_PITCH | FF_DONTCARE,
                L"Khmer OS Siemreap"
            );
        }

        if (candidate_window_) {
            SetWindowLongPtrW(candidate_window_, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(this));
        }
    }

    void hide_candidate_window()
    {
        if (candidate_window_) {
            KillTimer(candidate_window_, CANDIDATE_FETCH_TIMER_ID);
            ShowWindow(candidate_window_, SW_HIDE);
        }
    }

    void schedule_candidate_fetch(UINT delay_ms)
    {
        ensure_candidate_window();

        if (candidate_window_) {
            SetTimer(
                candidate_window_,
                CANDIDATE_FETCH_TIMER_ID,
                delay_ms,
                nullptr
            );
        }
    }

    void show_candidate_window_from_current_candidates()
    {
        if (candidates_.empty()) {
            selected_candidate_index_ = 0;
            hide_candidate_window();
            return;
        }

        if (selected_candidate_index_ >= candidates_.size()) {
            selected_candidate_index_ = candidates_.size() - 1;
        }

        ensure_candidate_window();

        if (!candidate_window_) {
            return;
        }

        size_t visible_count = visible_candidate_count_for_selection(selected_candidate_index_);
        int width = selected_candidate_index_ < 5 ? 360 : 460;
        int height = static_cast<int>(78 + visible_count * 42);

        position_candidate_window(candidate_window_, width, height);
        InvalidateRect(candidate_window_, nullptr, FALSE);
        write_key_event_log(L"Candidate popup updated", 0, 0);
    }

    void fetch_candidates_now()
    {
        if (candidate_window_) {
            KillTimer(candidate_window_, CANDIDATE_FETCH_TIMER_ID);
        }

        std::wstring fetch_buffer = pending_fetch_buffer_.empty()
            ? romanized_buffer_
            : pending_fetch_buffer_;

        pending_fetch_buffer_.clear();

        if (fetch_buffer.empty()) {
            return;
        }

        std::wstring previous_word = previous_committed_khmer_;
        std::wstring cache_key = suggestion_cache_key(fetch_buffer, previous_word);
        auto cached = suggestion_cache_.find(cache_key);

        if (cached != suggestion_cache_.end()) {
            if (fetch_buffer != romanized_buffer_) {
                return;
            }

            candidates_ = cached->second;
            candidate_fetch_retry_count_ = 0;
            selected_candidate_index_ = 0;
            hover_candidate_index_ = static_cast<size_t>(-1);
            show_candidate_window_from_current_candidates();
            return;
        }

        if (candidate_fetch_in_progress_) {
            pending_fetch_buffer_ = fetch_buffer;
            return;
        }

        ensure_candidate_window();

        if (!candidate_window_) {
            return;
        }

        CandidateFetchRequest* request = new (std::nothrow) CandidateFetchRequest();

        if (!request) {
            return;
        }

        request->window = candidate_window_;
        request->buffer = fetch_buffer;
        request->previous_word = previous_word;
        request->cache_key = cache_key;
        request->limit = 20;
        candidate_fetch_in_progress_ = true;

        HANDLE thread = CreateThread(
            nullptr,
            0,
            CandidateFetchThreadProc,
            request,
            0,
            nullptr
        );

        if (!thread) {
            candidate_fetch_in_progress_ = false;
            delete request;
            write_key_event_hresult_log(L"Candidate fetch CreateThread", HRESULT_FROM_WIN32(GetLastError()));
            return;
        }

        CloseHandle(thread);
    }

    void handle_candidate_fetch_complete(CandidateFetchResult* result)
    {
        candidate_fetch_in_progress_ = false;

        if (!result) {
            return;
        }

        std::wstring fetch_buffer = result->buffer;
        std::wstring previous_word = result->previous_word;
        std::wstring cache_key = result->cache_key;
        std::vector<std::wstring> fetched_suggestions = result->suggestions;
        delete result;

        if (!fetched_suggestions.empty()) {
            suggestion_cache_[cache_key] = fetched_suggestions;

            if (suggestion_cache_.size() > 128) {
                suggestion_cache_.erase(suggestion_cache_.begin());
            }
        }

        if (fetch_buffer != romanized_buffer_ || previous_word != previous_committed_khmer_) {
            if (!romanized_buffer_.empty()) {
                pending_fetch_buffer_ = romanized_buffer_;
                schedule_candidate_fetch(1);
            }

            return;
        }

        candidates_ = fetched_suggestions;

        if (candidates_.empty()) {
            if (candidate_fetch_retry_count_ < CANDIDATE_FETCH_MAX_RETRIES) {
                ++candidate_fetch_retry_count_;
                pending_fetch_buffer_ = fetch_buffer;
                schedule_candidate_fetch(CANDIDATE_FETCH_RETRY_MS);
            } else {
                hide_candidate_window();
            }

            return;
        }

        candidate_fetch_retry_count_ = 0;
        selected_candidate_index_ = 0;
        hover_candidate_index_ = static_cast<size_t>(-1);
        show_candidate_window_from_current_candidates();
    }

    void update_candidate_window()
    {
        if (romanized_buffer_.empty()) {
            candidates_.clear();
            pending_fetch_buffer_.clear();
            candidate_fetch_retry_count_ = 0;
            selected_candidate_index_ = 0;
            hover_candidate_index_ = static_cast<size_t>(-1);
            hide_candidate_window();
            return;
        }

        auto cached = suggestion_cache_.find(
            suggestion_cache_key(romanized_buffer_, previous_committed_khmer_)
        );

        if (cached != suggestion_cache_.end()) {
            candidates_ = cached->second;
            candidate_fetch_retry_count_ = 0;
            selected_candidate_index_ = 0;
            hover_candidate_index_ = static_cast<size_t>(-1);
            show_candidate_window_from_current_candidates();
            return;
        }

        candidate_fetch_retry_count_ = 0;
        pending_fetch_buffer_ = romanized_buffer_;
        schedule_candidate_fetch(CANDIDATE_FETCH_DEBOUNCE_MS);
    }

    bool commit_candidate_by_index(ITfContext* context, size_t index)
    {
        if (index >= candidates_.size()) {
            return false;
        }

        std::wstring committed_input = romanized_buffer_;
        std::wstring committed_khmer = candidates_[index];
        std::wstring previous_word = previous_committed_khmer_;
        request_text_replace(
            context,
            committed_khmer,
            static_cast<LONG>(romanized_buffer_.size()),
            L"OnKeyDown candidate popup commit",
            false,
            true
        );
        record_khmer_selection_async(committed_input, committed_khmer, previous_word);
        previous_committed_khmer_ = committed_khmer;
        suggestion_cache_.clear();
        romanized_buffer_.clear();
        candidates_.clear();
        pending_fetch_buffer_.clear();
        candidate_fetch_retry_count_ = 0;
        selected_candidate_index_ = 0;
        hide_candidate_window();
        return true;
    }

    void invalidate_candidate_row(size_t candidate_index, size_t page_start)
    {
        if (!candidate_window_ || candidate_index < page_start) {
            return;
        }

        size_t local_index = candidate_index - page_start;

        if (local_index >= visible_candidate_count_for_selection(selected_candidate_index_)) {
            return;
        }

        RECT client_rect = {};
        GetClientRect(candidate_window_, &client_rect);

        int row_top = candidate_padding() + static_cast<int>(local_index) * candidate_row_height();
        RECT row_rect = {
            candidate_padding() + candidate_gutter_width(),
            row_top,
            client_rect.right - candidate_padding(),
            row_top + candidate_row_height()
        };
        InvalidateRect(candidate_window_, &row_rect, FALSE);
    }

    void move_candidate_selection(int direction)
    {
        if (candidates_.empty()) {
            return;
        }

        size_t old_selection = selected_candidate_index_;
        size_t old_page_start = candidate_page_start_for_selection(selected_candidate_index_);
        size_t old_visible_count = visible_candidate_count_for_selection(selected_candidate_index_);

        if (direction > 0 && selected_candidate_index_ + 1 < candidates_.size()) {
            ++selected_candidate_index_;
        } else if (direction < 0 && selected_candidate_index_ > 0) {
            --selected_candidate_index_;
        }

        if (old_selection == selected_candidate_index_) {
            return;
        }

        size_t new_page_start = candidate_page_start_for_selection(selected_candidate_index_);
        size_t new_visible_count = visible_candidate_count_for_selection(selected_candidate_index_);

        if (old_page_start != new_page_start || old_visible_count != new_visible_count) {
            show_candidate_window_from_current_candidates();
            return;
        }

        invalidate_candidate_row(old_selection, old_page_start);
        invalidate_candidate_row(selected_candidate_index_, new_page_start);
    }

    bool candidate_index_from_y(int y, size_t* candidate_index)
    {
        if (!candidate_index || candidates_.empty()) {
            return false;
        }

        size_t page_start = candidate_page_start_for_selection(selected_candidate_index_);
        size_t visible_count = visible_candidate_count_for_selection(selected_candidate_index_);
        size_t page_end = min(candidates_.size(), page_start + visible_count);
        int top = candidate_padding();

        int row = (y - top) / candidate_row_height();

        if (row < 0) {
            return false;
        }

        size_t index = page_start + static_cast<size_t>(row);

        if (index >= page_end) {
            return false;
        }

        *candidate_index = index;
        return true;
    }

    void paint_candidate_window(HWND window)
    {
        PAINTSTRUCT paint = {};
        HDC paint_dc = BeginPaint(window, &paint);

        if (!paint_dc) {
            return;
        }

        RECT client_rect = {};
        GetClientRect(window, &client_rect);
        int width = client_rect.right - client_rect.left;
        int height = client_rect.bottom - client_rect.top;

        HDC draw_dc = CreateCompatibleDC(paint_dc);
        HBITMAP buffer_bitmap = nullptr;
        HBITMAP old_bitmap = nullptr;

        if (draw_dc && width > 0 && height > 0) {
            buffer_bitmap = CreateCompatibleBitmap(paint_dc, width, height);

            if (buffer_bitmap) {
                old_bitmap = reinterpret_cast<HBITMAP>(SelectObject(draw_dc, buffer_bitmap));
            }
        }

        if (!draw_dc || !buffer_bitmap) {
            if (draw_dc) {
                DeleteDC(draw_dc);
            }

            EndPaint(window, &paint);
            return;
        }

        HBRUSH background = CreateSolidBrush(RGB(20, 25, 32));
        FillRect(draw_dc, &client_rect, background);
        DeleteObject(background);

        HPEN border_pen = CreatePen(PS_SOLID, 1, RGB(76, 96, 110));
        HBRUSH null_brush = reinterpret_cast<HBRUSH>(GetStockObject(NULL_BRUSH));
        HPEN old_pen = reinterpret_cast<HPEN>(SelectObject(draw_dc, border_pen));
        HBRUSH old_brush = reinterpret_cast<HBRUSH>(SelectObject(draw_dc, null_brush));
        RoundRect(draw_dc, 0, 0, client_rect.right, client_rect.bottom, 18, 18);
        SelectObject(draw_dc, old_brush);
        SelectObject(draw_dc, old_pen);
        DeleteObject(border_pen);

        SetBkMode(draw_dc, TRANSPARENT);
        SetTextColor(draw_dc, RGB(235, 248, 255));

        HFONT old_font = nullptr;
        if (candidate_font_) {
            old_font = reinterpret_cast<HFONT>(SelectObject(draw_dc, candidate_font_));
        }

        size_t page_start = candidate_page_start_for_selection(selected_candidate_index_);
        size_t visible_count = visible_candidate_count_for_selection(selected_candidate_index_);
        size_t page_end = min(candidates_.size(), page_start + visible_count);
        int y = candidate_padding();
        int row_height = candidate_row_height();
        int gutter_width = candidate_gutter_width();

        RECT gutter_rect = {
            candidate_padding(),
            candidate_padding(),
            candidate_padding() + gutter_width,
            client_rect.bottom - candidate_padding()
        };
        HPEN gutter_pen = CreatePen(PS_SOLID, 1, RGB(67, 85, 98));
        HPEN previous_pen = reinterpret_cast<HPEN>(SelectObject(draw_dc, gutter_pen));
        MoveToEx(draw_dc, gutter_rect.left + gutter_width / 2, gutter_rect.top + 18, nullptr);
        LineTo(draw_dc, gutter_rect.left + gutter_width / 2, gutter_rect.bottom - 18);
        SelectObject(draw_dc, previous_pen);
        DeleteObject(gutter_pen);

        if (page_start > 0) {
            RECT up_rect = {gutter_rect.left, gutter_rect.top, gutter_rect.right, gutter_rect.top + 28};
            DrawTextW(draw_dc, L"^", -1, &up_rect, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        }

        for (size_t index = page_start; index < page_end; ++index) {
            RECT row_rect = {
                candidate_padding() + gutter_width,
                y,
                client_rect.right - candidate_padding(),
                y + row_height
            };

            if (index == selected_candidate_index_ || index == hover_candidate_index_) {
                HBRUSH selected_brush = CreateSolidBrush(
                    index == selected_candidate_index_ ? RGB(58, 91, 114) : RGB(45, 58, 72)
                );
                FillRect(draw_dc, &row_rect, selected_brush);
                DeleteObject(selected_brush);
            }

            size_t local_number = index - page_start + 1;
            std::wstring row_text = std::to_wstring(local_number) + L"  ";
            row_text += candidates_[index];

            RECT text_rect = row_rect;
            text_rect.left += 8;
            DrawTextW(draw_dc, row_text.c_str(), -1, &text_rect, DT_LEFT | DT_VCENTER | DT_SINGLELINE);
            y += row_height;
        }

        if (page_end < candidates_.size()) {
            RECT down_rect = {gutter_rect.left, gutter_rect.bottom - 28, gutter_rect.right, gutter_rect.bottom};
            DrawTextW(draw_dc, L"v", -1, &down_rect, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        }

        if (old_font) {
            SelectObject(draw_dc, old_font);
        }

        BitBlt(paint_dc, 0, 0, width, height, draw_dc, 0, 0, SRCCOPY);
        SelectObject(draw_dc, old_bitmap);
        DeleteObject(buffer_bitmap);
        DeleteDC(draw_dc);
        EndPaint(window, &paint);
    }

    void handle_candidate_mouse_move(HWND window, LPARAM lparam)
    {
        size_t hovered = static_cast<size_t>(-1);
        int y = static_cast<short>(HIWORD(lparam));

        if (!candidate_index_from_y(y, &hovered)) {
            hovered = static_cast<size_t>(-1);
        }

        if (hover_candidate_index_ != hovered) {
            hover_candidate_index_ = hovered;
            InvalidateRect(window, nullptr, FALSE);
        }

        TRACKMOUSEEVENT track_event = {};
        track_event.cbSize = sizeof(TRACKMOUSEEVENT);
        track_event.dwFlags = TME_LEAVE;
        track_event.hwndTrack = window;
        TrackMouseEvent(&track_event);
    }

    void handle_candidate_mouse_leave(HWND window)
    {
        if (hover_candidate_index_ != static_cast<size_t>(-1)) {
            hover_candidate_index_ = static_cast<size_t>(-1);
            InvalidateRect(window, nullptr, FALSE);
        }
    }

    void handle_candidate_click(LPARAM lparam)
    {
        size_t clicked_index = 0;
        int y = static_cast<short>(HIWORD(lparam));

        if (candidate_index_from_y(y, &clicked_index)) {
            selected_candidate_index_ = clicked_index;
            commit_candidate_by_index(last_context_, clicked_index);
        }
    }

    LRESULT handle_candidate_window_message(HWND window, UINT message, WPARAM wparam, LPARAM lparam)
    {
        switch (message) {
        case WM_PAINT:
            paint_candidate_window(window);
            return 0;
        case WM_ERASEBKGND:
            return 1;
        case WM_TIMER:
            if (wparam == CANDIDATE_FETCH_TIMER_ID) {
                fetch_candidates_now();
                return 0;
            }
            break;
        case CANDIDATE_FETCH_COMPLETE_MESSAGE:
            handle_candidate_fetch_complete(reinterpret_cast<CandidateFetchResult*>(lparam));
            return 0;
        case WM_MOUSEMOVE:
            handle_candidate_mouse_move(window, lparam);
            return 0;
        case WM_MOUSELEAVE:
            handle_candidate_mouse_leave(window);
            return 0;
        case WM_LBUTTONDOWN:
            handle_candidate_click(lparam);
            return 0;
        default:
            return DefWindowProcW(window, message, wparam, lparam);
        }
    }

    STDMETHODIMP OnTestKeyDown(ITfContext* context, WPARAM wparam, LPARAM lparam, BOOL* eaten) override
    {
        bool has_buffer = !romanized_buffer_.empty();
        bool should_eat =
            is_alpha_key(wparam) ||
            (wparam == VK_SPACE && has_buffer) ||
            (is_commit_key(wparam) && has_buffer) ||
            (is_buffer_control_key(wparam) && has_buffer) ||
            ((wparam == VK_UP || wparam == VK_DOWN) && !candidates_.empty()) ||
            (((wparam >= L'1' && wparam <= L'9') || wparam == L'0') && !candidates_.empty());

        write_key_event_log(L"OnTestKeyDown", wparam, lparam);

        if (eaten) {
            *eaten = should_eat;
        }

        return S_OK;
    }

    STDMETHODIMP OnKeyDown(ITfContext* context, WPARAM wparam, LPARAM lparam, BOOL* eaten) override
    {
        remember_context(context);

        bool has_buffer = !romanized_buffer_.empty();
        bool should_eat =
            is_alpha_key(wparam) ||
            (wparam == VK_SPACE && has_buffer) ||
            (is_commit_key(wparam) && has_buffer) ||
            (is_buffer_control_key(wparam) && has_buffer) ||
            ((wparam == VK_UP || wparam == VK_DOWN) && !candidates_.empty()) ||
            (((wparam >= L'1' && wparam <= L'9') || wparam == L'0') && !candidates_.empty());

        if (eaten) {
            *eaten = should_eat;
        }

        write_key_event_log(L"OnKeyDown", wparam, lparam);

        if (is_alpha_key(wparam) || (wparam == VK_SPACE && !romanized_buffer_.empty())) {
            wchar_t buffer_char = key_to_buffer_char(wparam);

            if (buffer_char) {
                romanized_buffer_ += buffer_char;
                std::wstring inserted_text(1, buffer_char);
                request_text_replace(
                    context,
                    inserted_text,
                    0,
                    L"OnKeyDown composition update",
                    true,
                    false
                );
            }

            selected_candidate_index_ = 0;
            write_key_event_log(L"Romanized buffer appended", wparam, lparam);
            update_candidate_window();
        } else if (((wparam >= L'1' && wparam <= L'9') || wparam == L'0') && !candidates_.empty()) {
            size_t local_index = wparam == L'0'
                ? 9
                : static_cast<size_t>(wparam - L'1');
            size_t index = candidate_page_start_for_selection(selected_candidate_index_) + local_index;
            commit_candidate_by_index(context, index);
        } else if (is_commit_key(wparam) && !romanized_buffer_.empty()) {
            if (!commit_candidate_by_index(context, selected_candidate_index_)) {
                request_text_replace(
                    context,
                    romanized_buffer_,
                    static_cast<LONG>(romanized_buffer_.size()),
                    L"OnKeyDown raw buffer commit",
                    false,
                    true
                );
                previous_committed_khmer_.clear();
                romanized_buffer_.clear();
                selected_candidate_index_ = 0;
                hide_candidate_window();
            }
        } else if (wparam == VK_BACK && !romanized_buffer_.empty()) {
            romanized_buffer_.pop_back();
            request_text_replace(
                context,
                L"",
                1,
                L"OnKeyDown composition backspace",
                !romanized_buffer_.empty(),
                romanized_buffer_.empty()
            );
            selected_candidate_index_ = 0;
            write_key_event_log(L"Romanized buffer backspace", wparam, lparam);
            update_candidate_window();
        } else if (wparam == VK_DOWN) {
            move_candidate_selection(1);
        } else if (wparam == VK_UP) {
            move_candidate_selection(-1);
        } else if (wparam == VK_ESCAPE) {
            request_text_replace(
                context,
                L"",
                static_cast<LONG>(romanized_buffer_.size()),
                L"OnKeyDown composition clear",
                false,
                true
            );
            romanized_buffer_.clear();
            candidates_.clear();
            selected_candidate_index_ = 0;
            hide_candidate_window();
            write_key_event_log(L"Romanized buffer cleared", wparam, lparam);
        }

        return S_OK;
    }

    STDMETHODIMP OnTestKeyUp(ITfContext*, WPARAM wparam, LPARAM lparam, BOOL* eaten) override
    {
        if (eaten) {
            *eaten = is_alpha_key(wparam) || is_commit_key(wparam) || is_buffer_control_key(wparam) || ((wparam == VK_UP || wparam == VK_DOWN) && !candidates_.empty()) || (((wparam >= L'1' && wparam <= L'9') || wparam == L'0') && !candidates_.empty());
        }

        write_key_event_log(L"OnTestKeyUp", wparam, lparam);
        return S_OK;
    }

    STDMETHODIMP OnKeyUp(ITfContext*, WPARAM wparam, LPARAM lparam, BOOL* eaten) override
    {
        if (eaten) {
            *eaten = is_alpha_key(wparam) || is_commit_key(wparam) || is_buffer_control_key(wparam) || ((wparam == VK_UP || wparam == VK_DOWN) && !candidates_.empty()) || (((wparam >= L'1' && wparam <= L'9') || wparam == L'0') && !candidates_.empty());
        }

        write_key_event_log(L"OnKeyUp", wparam, lparam);
        return S_OK;
    }

    STDMETHODIMP OnPreservedKey(ITfContext*, REFGUID, BOOL* eaten) override
    {
        if (eaten) {
            *eaten = FALSE;
        }

        write_key_event_log(L"OnPreservedKey", 0, 0);
        return S_OK;
    }

private:
    long ref_count_;
    ITfThreadMgr* thread_manager_;
    ITfKeystrokeMgr* keystroke_manager_;
    TfClientId client_id_;
    std::wstring romanized_buffer_;
    HWND candidate_window_;
    HFONT candidate_font_;
    std::vector<std::wstring> candidates_;
    size_t selected_candidate_index_;
    size_t hover_candidate_index_;
    std::map<std::wstring, std::vector<std::wstring>> suggestion_cache_;
    std::wstring pending_fetch_buffer_;
    int candidate_fetch_retry_count_;
    bool candidate_fetch_in_progress_;
    std::wstring previous_committed_khmer_;
    ITfContext* last_context_;
    ITfComposition* composition_;
};

LRESULT CALLBACK CandidateWindowProc(HWND window, UINT message, WPARAM wparam, LPARAM lparam)
{
    SkeletonTextService* service = reinterpret_cast<SkeletonTextService*>(
        GetWindowLongPtrW(window, GWLP_USERDATA)
    );

    if (message == WM_NCCREATE) {
        CREATESTRUCTW* create = reinterpret_cast<CREATESTRUCTW*>(lparam);
        service = reinterpret_cast<SkeletonTextService*>(create->lpCreateParams);
        SetWindowLongPtrW(window, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(service));
    }

    if (service) {
        return service->handle_candidate_window_message(window, message, wparam, lparam);
    }

    return DefWindowProcW(window, message, wparam, lparam);
}

class SkeletonClassFactory : public IClassFactory
{
public:
    SkeletonClassFactory()
        : ref_count_(1)
    {
        ++g_object_count;
    }

    ~SkeletonClassFactory()
    {
        --g_object_count;
    }

    STDMETHODIMP QueryInterface(REFIID riid, void** object) override
    {
        if (!object) {
            return E_POINTER;
        }

        *object = nullptr;

        if (riid == IID_IUnknown || riid == IID_IClassFactory) {
            *object = static_cast<IClassFactory*>(this);
            AddRef();
            return S_OK;
        }

        return E_NOINTERFACE;
    }

    STDMETHODIMP_(ULONG) AddRef() override
    {
        return InterlockedIncrement(&ref_count_);
    }

    STDMETHODIMP_(ULONG) Release() override
    {
        ULONG ref_count = InterlockedDecrement(&ref_count_);

        if (ref_count == 0) {
            delete this;
        }

        return ref_count;
    }

    STDMETHODIMP CreateInstance(IUnknown* outer, REFIID riid, void** object) override
    {
        if (!object) {
            return E_POINTER;
        }

        *object = nullptr;

        if (outer) {
            return CLASS_E_NOAGGREGATION;
        }

        SkeletonTextService* service = new (std::nothrow) SkeletonTextService();

        if (!service) {
            return E_OUTOFMEMORY;
        }

        HRESULT result = service->QueryInterface(riid, object);
        service->Release();
        return result;
    }

    STDMETHODIMP LockServer(BOOL lock) override
    {
        if (lock) {
            ++g_lock_count;
        } else {
            --g_lock_count;
        }

        return S_OK;
    }

private:
    long ref_count_;
};

BOOL APIENTRY DllMain(HINSTANCE instance, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH) {
        g_module = instance;
        DisableThreadLibraryCalls(instance);
    }

    return TRUE;
}

STDAPI DllCanUnloadNow()
{
    return (g_object_count == 0 && g_lock_count == 0) ? S_OK : S_FALSE;
}

STDAPI DllGetClassObject(REFCLSID clsid, REFIID riid, void** object)
{
    if (clsid != CLSID_KhmerImeSkeleton) {
        return CLASS_E_CLASSNOTAVAILABLE;
    }

    SkeletonClassFactory* factory = new (std::nothrow) SkeletonClassFactory();

    if (!factory) {
        return E_OUTOFMEMORY;
    }

    HRESULT result = factory->QueryInterface(riid, object);
    factory->Release();
    return result;
}

HRESULT set_registry_string(HKEY root, const wchar_t* path, const wchar_t* name, const wchar_t* value)
{
    HKEY key = nullptr;
    LONG result = RegCreateKeyExW(
        root,
        path,
        0,
        nullptr,
        REG_OPTION_NON_VOLATILE,
        KEY_WRITE,
        nullptr,
        &key,
        nullptr
    );

    if (result != ERROR_SUCCESS) {
        return HRESULT_FROM_WIN32(result);
    }

    result = RegSetValueExW(
        key,
        name,
        0,
        REG_SZ,
        reinterpret_cast<const BYTE*>(value),
        static_cast<DWORD>((wcslen(value) + 1) * sizeof(wchar_t))
    );

    RegCloseKey(key);
    return HRESULT_FROM_WIN32(result);
}

bool should_uninitialize_com(HRESULT result)
{
    return SUCCEEDED(result);
}

HRESULT register_tsf_profile(const wchar_t* module_path)
{
    HRESULT com_result = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    bool uninitialize_com = should_uninitialize_com(com_result);
    write_registration_log(L"CoInitializeEx(register_tsf_profile)", com_result);

    if (FAILED(com_result) && com_result != RPC_E_CHANGED_MODE) {
        return com_result;
    }

    ITfInputProcessorProfiles* profiles = nullptr;
    HRESULT result = CoCreateInstance(
        CLSID_TF_InputProcessorProfiles,
        nullptr,
        CLSCTX_INPROC_SERVER,
        IID_ITfInputProcessorProfiles,
        reinterpret_cast<void**>(&profiles)
    );
    write_registration_log(L"CoCreateInstance(CLSID_TF_InputProcessorProfiles)", result);

    if (SUCCEEDED(result)) {
        result = profiles->Register(CLSID_KhmerImeSkeleton);
        write_registration_log(L"ITfInputProcessorProfiles::Register", result);
    }

    if (SUCCEEDED(result)) {
        result = profiles->AddLanguageProfile(
            CLSID_KhmerImeSkeleton,
            KHMER_CAMBODIA_LANGID,
            GUID_KhmerImeProfile,
            KHMER_IME_SERVICE_DESCRIPTION,
            static_cast<ULONG>(wcslen(KHMER_IME_SERVICE_DESCRIPTION)),
            nullptr,
            0,
            0
        );
        write_registration_log(L"ITfInputProcessorProfiles::AddLanguageProfile", result);
    }

    if (SUCCEEDED(result)) {
        result = profiles->EnableLanguageProfile(
            CLSID_KhmerImeSkeleton,
            KHMER_CAMBODIA_LANGID,
            GUID_KhmerImeProfile,
            TRUE
        );
        write_registration_log(L"ITfInputProcessorProfiles::EnableLanguageProfile", result);
    }

    if (profiles) {
        profiles->Release();
    }

    ITfCategoryMgr* category_manager = nullptr;

    if (SUCCEEDED(result)) {
        result = CoCreateInstance(
            CLSID_TF_CategoryMgr,
            nullptr,
            CLSCTX_INPROC_SERVER,
            IID_ITfCategoryMgr,
            reinterpret_cast<void**>(&category_manager)
        );
        write_registration_log(L"CoCreateInstance(CLSID_TF_CategoryMgr)", result);
    }

    if (SUCCEEDED(result)) {
        result = category_manager->RegisterCategory(
            CLSID_KhmerImeSkeleton,
            GUID_TFCAT_TIP_KEYBOARD,
            CLSID_KhmerImeSkeleton
        );
        write_registration_log(L"ITfCategoryMgr::RegisterCategory", result);
    }

    if (category_manager) {
        category_manager->Release();
    }

    if (uninitialize_com) {
        CoUninitialize();
    }

    return result;
}

HRESULT unregister_tsf_profile()
{
    HRESULT com_result = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    bool uninitialize_com = should_uninitialize_com(com_result);
    write_registration_log(L"CoInitializeEx(unregister_tsf_profile)", com_result);

    if (FAILED(com_result) && com_result != RPC_E_CHANGED_MODE) {
        return com_result;
    }

    ITfCategoryMgr* category_manager = nullptr;
    HRESULT result = CoCreateInstance(
        CLSID_TF_CategoryMgr,
        nullptr,
        CLSCTX_INPROC_SERVER,
        IID_ITfCategoryMgr,
        reinterpret_cast<void**>(&category_manager)
    );
    write_registration_log(L"CoCreateInstance(CLSID_TF_CategoryMgr unregister)", result);

    if (SUCCEEDED(result)) {
        result = category_manager->UnregisterCategory(
            CLSID_KhmerImeSkeleton,
            GUID_TFCAT_TIP_KEYBOARD,
            CLSID_KhmerImeSkeleton
        );
        write_registration_log(L"ITfCategoryMgr::UnregisterCategory", result);
    }

    if (category_manager) {
        category_manager->Release();
    }

    ITfInputProcessorProfiles* profiles = nullptr;
    HRESULT profile_result = CoCreateInstance(
        CLSID_TF_InputProcessorProfiles,
        nullptr,
        CLSCTX_INPROC_SERVER,
        IID_ITfInputProcessorProfiles,
        reinterpret_cast<void**>(&profiles)
    );
    write_registration_log(L"CoCreateInstance(CLSID_TF_InputProcessorProfiles unregister)", profile_result);

    if (SUCCEEDED(profile_result)) {
        profiles->EnableLanguageProfile(
            CLSID_KhmerImeSkeleton,
            KHMER_CAMBODIA_LANGID,
            GUID_KhmerImeProfile,
            FALSE
        );
        profiles->RemoveLanguageProfile(
            CLSID_KhmerImeSkeleton,
            KHMER_CAMBODIA_LANGID,
            GUID_KhmerImeProfile
        );
        profile_result = profiles->Unregister(CLSID_KhmerImeSkeleton);
        write_registration_log(L"ITfInputProcessorProfiles::Unregister", profile_result);
    }

    if (profiles) {
        profiles->Release();
    }

    if (uninitialize_com) {
        CoUninitialize();
    }

    if (FAILED(result) && result != E_FAIL) {
        return result;
    }

    return profile_result;
}

STDAPI DllRegisterServer()
{
    clear_registration_log();

    wchar_t module_path[MAX_PATH] = {};

    if (!GetModuleFileNameW(g_module, module_path, MAX_PATH)) {
        return HRESULT_FROM_WIN32(GetLastError());
    }

    const wchar_t* clsid_path =
        L"Software\\Classes\\CLSID\\{4A5D6F23-A20A-46A4-9CCB-1A7C37D91E30}";
    const wchar_t* inproc_path =
        L"Software\\Classes\\CLSID\\{4A5D6F23-A20A-46A4-9CCB-1A7C37D91E30}\\InprocServer32";

    HRESULT result = set_registry_string(
        HKEY_CURRENT_USER,
        clsid_path,
        nullptr,
        L"Khmer Romanized IME TSF Skeleton"
    );
    write_registration_log(L"COM registry CLSID", result);

    if (FAILED(result)) {
        return result;
    }

    result = set_registry_string(
        HKEY_CURRENT_USER,
        inproc_path,
        nullptr,
        module_path
    );
    write_registration_log(L"COM registry InprocServer32", result);

    if (FAILED(result)) {
        return result;
    }

    result = set_registry_string(
        HKEY_CURRENT_USER,
        inproc_path,
        L"ThreadingModel",
        L"Apartment"
    );
    write_registration_log(L"COM registry ThreadingModel", result);

    if (FAILED(result)) {
        return result;
    }

    return register_tsf_profile(module_path);
}

STDAPI DllUnregisterServer()
{
    unregister_tsf_profile();

    LONG result = RegDeleteTreeW(
        HKEY_CURRENT_USER,
        L"Software\\Classes\\CLSID\\{4A5D6F23-A20A-46A4-9CCB-1A7C37D91E30}"
    );

    if (result == ERROR_FILE_NOT_FOUND || result == ERROR_SUCCESS) {
        return S_OK;
    }

    return HRESULT_FROM_WIN32(result);
}
