// 函数声明

typedef unsigned long DWORD;

DWORD getAbsoluteAddress(const char *libraryName, DWORD relativeAddr);

bool isLibraryLoaded(const char *libraryName);

uintptr_t string2Offset(const char *c);

uintptr_t findSymbolAddress(const char *TargetLibName, const char *sym);