#include <fcntl.h>
#include <io.h>
#include <iostream>

int wmain()
{
    _setmode(_fileno(stdout), _O_U16TEXT);

    std::wcout << L"Khmer IME C++ smoke test\n";
    std::wcout << L"k -> \u1780\n";

    return 0;
}
