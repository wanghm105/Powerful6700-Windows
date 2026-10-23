/* Read-only range reader for the A6700 maintenance process.
 *
 * It is loaded through Jiritsu SET_FILE(file 2) as libJit.so and runs as a
 * constructor. It only ever opens files O_RDONLY: there is no write syscall
 * path, so this payload cannot modify the camera.
 *
 * Request file (Jiritsu SET_FILE2, file 0) and result file share one path:
 *   0  "A67D"
 *   4  u32 version = 1
 *   8  u32 mode     0 = read range, 1 = report size
 *  12  u32 path_len
 *  16  u64 offset
 *  24  u32 length
 *  28  path bytes (no NUL)
 *
 * Result (same path):
 *   0  "A67D"
 *   4  u32 version
 *   8  u32 status   0 ok, 1 bad request, 2 open failed, 3 read failed,
 *                  4 path too long, 5 lseek failed
 *  12  u32 mode
 *  16  u64 size
 *  24  u32 length
 *  28  data
 */
#define HEADER 28u
#define PATH_MAX 192u
#define DATA_MAX 0x100000u
#define AT_FDCWD -100L
#define SYS_CLOSE 57L
#define SYS_PREAD64 67L
#define SYS_OPENAT 56L
#define SYS_WRITE 64L
#define SYS_FSYNC 82L
#define SYS_LSEEK 62L
#define SEEK_END 2L

static const char result_path[] = "/tmp/jiritsu/tmmc.jit";
static unsigned char request[HEADER + PATH_MAX];
static unsigned char result[HEADER + DATA_MAX];
static char path_buf[PATH_MAX + 1u];

static long call4(long n, long a, long b, long c, long d) {
    register long x8 __asm__("x8") = n;
    register long x0 __asm__("x0") = a;
    register long x1 __asm__("x1") = b;
    register long x2 __asm__("x2") = c;
    register long x3 __asm__("x3") = d;
    __asm__ volatile("svc #0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2), "r"(x3) : "memory");
    return x0;
}

/* Bound EINTR and short I/O; zero-length progress is a failure. */
static int io(long syscall, long fd, unsigned char *buf, unsigned long size, unsigned long off) {
    unsigned long done = 0;
    unsigned attempts = 0;
    while (done < size && attempts++ < 1024) {
        long n = call4(syscall, fd, (long)(buf + done), (long)(size - done), (long)(off + done));
        if (n == -4) continue;
        if (n <= 0 || (unsigned long)n > size - done) return 0;
        done += (unsigned long)n;
    }
    return done == size;
}

static unsigned get32(unsigned off) {
    return (unsigned)request[off] | ((unsigned)request[off + 1] << 8)
         | ((unsigned)request[off + 2] << 16) | ((unsigned)request[off + 3] << 24);
}
static unsigned long long get64(unsigned off) {
    return (unsigned long long)get32(off) | ((unsigned long long)get32(off + 4) << 32);
}
static void put32(unsigned off, unsigned value) {
    for (unsigned i = 0; i < 4; i++) result[off + i] = (unsigned char)(value >> (8 * i));
}
static void put64(unsigned off, unsigned long long value) {
    for (unsigned i = 0; i < 8; i++) result[off + i] = (unsigned char)(value >> (8 * i));
}
static int same4(const unsigned char *p, const char *m) {
    for (unsigned i = 0; i < 4; i++) if (p[i] != (unsigned char)m[i]) return 0;
    return 1;
}

static void publish(unsigned status, unsigned mode, unsigned long long size, unsigned length) {
    result[0] = 'A'; result[1] = '6'; result[2] = '7'; result[3] = 'D';
    put32(4, 1);
    put32(8, status);
    put32(12, mode);
    put64(16, size);
    put32(24, length);
    long fd = call4(SYS_OPENAT, AT_FDCWD, (long)result_path, 0x241, 0600);
    if (fd < 0) return;
    if (io(SYS_WRITE, fd, result, HEADER + length, 0)) call4(SYS_FSYNC, fd, 0, 0, 0);
    call4(SYS_CLOSE, fd, 0, 0, 0);
}

__attribute__((constructor)) static void run(void) {
    long fd = call4(SYS_OPENAT, AT_FDCWD, (long)result_path, 0, 0);
    if (fd < 0) return;
    int ok = io(SYS_PREAD64, fd, request, HEADER, 0);
    call4(SYS_CLOSE, fd, 0, 0, 0);
    if (!ok || !same4(request, "A67D") || get32(4) != 1) { publish(1, 0, 0, 0); return; }

    unsigned mode = get32(8);
    unsigned path_len = get32(12);
    unsigned length = get32(24);
    if (path_len == 0 || path_len > PATH_MAX || mode > 1 || (mode == 0 && length > DATA_MAX)) {
        publish(4, mode, 0, 0);
        return;
    }
    fd = call4(SYS_OPENAT, AT_FDCWD, (long)result_path, 0, 0);
    if (fd < 0) { publish(2, mode, 0, 0); return; }
    ok = io(SYS_PREAD64, fd, request + HEADER, path_len, HEADER);
    call4(SYS_CLOSE, fd, 0, 0, 0);
    if (!ok) { publish(1, mode, 0, 0); return; }
    for (unsigned i = 0; i < path_len; i++) path_buf[i] = (char)request[HEADER + i];
    path_buf[path_len] = 0;

    long file = call4(SYS_OPENAT, AT_FDCWD, (long)path_buf, 0, 0);
    if (file < 0) { publish(2, mode, 0, 0); return; }

    if (mode == 1) {
        long end = call4(SYS_LSEEK, file, 0, SEEK_END, 0);
        call4(SYS_CLOSE, file, 0, 0, 0);
        if (end < 0) { publish(5, mode, 0, 0); return; }
        publish(0, mode, (unsigned long long)end, 0);
        return;
    }

    unsigned long long offset = get64(16);
    unsigned char *dst = result + HEADER;
    int read_ok = io(SYS_PREAD64, file, dst, length, (unsigned long)offset);
    call4(SYS_CLOSE, file, 0, 0, 0);
    if (!read_ok) { publish(3, mode, 0, 0); return; }
    publish(0, mode, 0, length);
}
