/* Read-only camera-side payload for the Powerful6700 Windows port.
 *
 * Purpose: let the host inspect the maintenance environment and copy byte
 * ranges out of the camera's plaintext volumes, so the feature research can
 * look at what is really on the device instead of at an encrypted update file.
 *
 * Safety contract, checked by tools/verify_payload.py against this source and
 * against the compiled object:
 *   - the only write syscall is SYS_WRITE, and it is only issued for the
 *     result file below;
 *   - every other file is opened with flags 0 (O_RDONLY);
 *   - no mount, no ioctl, no partition write, no sysfs access, no pwrite64.
 *
 * Linux aarch64 asm-generic syscall ABI, no libc, no dynamic relocations.
 */
#define AT_FDCWD -100L
#define SYS_OPENAT 56L
#define SYS_CLOSE 57L
#define SYS_READ 63L
#define SYS_WRITE 64L
#define SYS_PREAD64 67L
#define SYS_NEWFSTATAT 79L
#define SYS_FSYNC 82L

#define O_RDONLY 0
#define O_WRONLY 1
#define O_CREAT 0100
#define O_TRUNC 01000

#define CFG_HEADER 20u
#define PATH_MAX_BYTES 512u
#define RESULT_HEADER 12u
#define RESULT_CAPACITY 786432u

static long call4(long n, long a, long b, long c, long d) {
    register long x8 __asm__("x8") = n;
    register long x0 __asm__("x0") = a;
    register long x1 __asm__("x1") = b;
    register long x2 __asm__("x2") = c;
    register long x3 __asm__("x3") = d;
    __asm__ volatile("svc #0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2), "r"(x3) : "memory");
    return x0;
}

static unsigned char input[CFG_HEADER + PATH_MAX_BYTES + 1u];
static unsigned char output[RESULT_HEADER + RESULT_CAPACITY];
static unsigned char scratch[512];
static unsigned char statbuf[256];
static unsigned out_cursor;

static const char result_path[] = "/tmp/jiritsu/tmmc.jit";

static unsigned long slen(const char *s) {
    unsigned long n = 0;
    while (s[n]) n++;
    return n;
}

static int same(const unsigned char *a, const char *b, unsigned long n) {
    for (unsigned long i = 0; i < n; i++)
        if (a[i] != (unsigned char)b[i]) return 0;
    return 1;
}

static unsigned get32(unsigned off) {
    return (unsigned)input[off] | ((unsigned)input[off + 1] << 8) |
           ((unsigned)input[off + 2] << 16) | ((unsigned)input[off + 3] << 24);
}

static void out32(unsigned off, unsigned value) {
    for (unsigned i = 0; i < 4; i++) output[off + i] = (unsigned char)(value >> (8 * i));
}

static unsigned long get64(const unsigned char *p) {
    unsigned long value = 0;
    for (unsigned i = 0; i < 8; i++) value |= (unsigned long)p[i] << (8 * i);
    return value;
}

/* Bound EINTR/short I/O; a zero-length progress is always a failure. */
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

static void emit_bytes(const unsigned char *data, unsigned long n) {
    if (out_cursor + n > RESULT_CAPACITY) return;
    for (unsigned long i = 0; i < n; i++) output[RESULT_HEADER + out_cursor + i] = data[i];
    out_cursor += (unsigned)n;
}

static void emit(const char *text) { emit_bytes((const unsigned char *)text, slen(text)); }

static void emit_unsigned(unsigned long value) {
    char digits[24];
    unsigned n = 0;
    if (!value) digits[n++] = '0';
    while (value) { digits[n++] = (char)('0' + value % 10u); value /= 10u; }
    char text[24];
    for (unsigned i = 0; i < n; i++) text[i] = digits[n - 1u - i];
    emit_bytes((const unsigned char *)text, n);
}

static void emit_hex(unsigned long value, unsigned digits) {
    static const char table[] = "0123456789abcdef";
    char text[17];
    if (digits > 16) digits = 16;
    for (unsigned i = 0; i < digits; i++) text[i] = table[(value >> (4u * (digits - 1u - i))) & 0xFu];
    emit_bytes((const unsigned char *)text, digits);
}

static int finish(unsigned status) {
    out32(0, 0x4252504Du); /* "MPRB", little endian */
    out32(4, status);
    out32(8, out_cursor);
    long fd = call4(SYS_OPENAT, AT_FDCWD, (long)result_path, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) return 0;
    int ok = io(SYS_WRITE, fd, output, RESULT_HEADER + out_cursor, 0);
    if (ok) call4(SYS_FSYNC, fd, 0, 0, 0);
    call4(SYS_CLOSE, fd, 0, 0, 0);
    return ok;
}

/* Read the whole request file; its length is part of the contract, so a size
 * mismatch is reported instead of being partially parsed. */
static int read_request(unsigned *size_out) {
    long rc = call4(SYS_NEWFSTATAT, AT_FDCWD, (long)result_path, (long)statbuf, 0);
    if (rc < 0) return 0;
    unsigned long size = get64(statbuf + 48);
    if (size < CFG_HEADER || size > CFG_HEADER + PATH_MAX_BYTES) return 0;
    long fd = call4(SYS_OPENAT, AT_FDCWD, (long)result_path, O_RDONLY, 0);
    if (fd < 0) return 0;
    int ok = io(SYS_READ, fd, input, size, 0);
    unsigned char extra;
    if (ok && call4(SYS_READ, fd, (long)&extra, 1, 0) != 0) ok = 0;
    call4(SYS_CLOSE, fd, 0, 0, 0);
    if (ok) *size_out = (unsigned)size;
    return ok;
}

static void report_stat(const char *path) {
    long rc = call4(SYS_NEWFSTATAT, AT_FDCWD, (long)path, (long)statbuf, 0);
    emit("stat ");
    emit(path);
    if (rc < 0) {
        emit(" error=");
        emit_unsigned((unsigned long)(-rc));
        emit("\n");
        return;
    }
    unsigned mode = (unsigned)statbuf[16] | ((unsigned)statbuf[17] << 8) |
                    ((unsigned)statbuf[18] << 16) | ((unsigned)statbuf[19] << 24);
    emit(" mode=0");
    emit_hex(mode, 6);
    emit(" size=");
    emit_unsigned(get64(statbuf + 48));
    emit(" inode=");
    emit_unsigned(get64(statbuf + 8));
    emit(" nlink=");
    emit_unsigned((unsigned)statbuf[20] | ((unsigned)statbuf[21] << 8) |
                  ((unsigned)statbuf[22] << 16) | ((unsigned)statbuf[23] << 24));
    emit("\n");
}

static void report_text_file(const char *path, const char *label) {
    long fd = call4(SYS_OPENAT, AT_FDCWD, (long)path, O_RDONLY, 0);
    emit(label);
    emit(" ");
    emit(path);
    emit("\n");
    if (fd < 0) {
        emit(" (open failed)\n");
        return;
    }
    for (unsigned round = 0; round < 32; round++) {
        long n = call4(SYS_READ, fd, (long)scratch, (long)sizeof(scratch), 0);
        if (n <= 0) break;
        emit_bytes(scratch, (unsigned long)n);
        if ((unsigned long)n < sizeof(scratch)) break;
    }
    emit("\n");
    call4(SYS_CLOSE, fd, 0, 0, 0);
}

/* command 0: environment report. command 1: raw byte range of one path. */
__attribute__((constructor)) static void run(void) {
    out_cursor = 0;
    out32(0, 0x4252504Du);
    out32(4, 0);
    out32(8, 0);

    unsigned size = 0;
    if (!read_request(&size)) { finish(3); return; }
    if (!same(input, "A67C", 4)) { finish(3); return; }
    unsigned command = get32(4);
    unsigned offset = get32(8);
    unsigned length = get32(12);
    unsigned path_len = get32(16);
    input[size] = 0;

    const char *path = (const char *)(input + CFG_HEADER);

    if (command == 0) {
        emit("Powerful6700 read-only probe\n");
        emit("command=info path_len=");
        emit_unsigned(path_len);
        emit("\n");
        report_text_file("/proc/mounts", "file");
        report_text_file("/proc/meminfo", "file");
        report_text_file("/proc/version", "file");
        report_stat("/usr/lib/appFw.so");
        report_stat("/cp/cpapp-b.bin");
        report_stat("/usr/lib");
        report_stat("/dev/nflasha15");
        report_stat("/dev/nflasha5");
        report_stat("/tmp/jiritsu");
        report_stat(path);
        finish(0);
        return;
    }

    if (command == 1) {
        if (!length || length > RESULT_CAPACITY) { finish(3); return; }
        long fd = call4(SYS_OPENAT, AT_FDCWD, (long)path, O_RDONLY, 0);
        if (fd < 0) { finish(1); return; }
        unsigned long done = 0;
        int ok = 1;
        while (done < length) {
            unsigned chunk = (unsigned)(length - done);
            long n = call4(SYS_PREAD64, fd, (long)(output + RESULT_HEADER + done), (long)chunk,
                           (long)(offset + done));
            if (n == -4) continue;
            if (n <= 0) { ok = 0; break; }
            done += (unsigned long)n;
        }
        call4(SYS_CLOSE, fd, 0, 0, 0);
        if (!ok) { finish(2); return; }
        out_cursor = (unsigned)done;
        finish(0);
        return;
    }

    finish(3);
}
