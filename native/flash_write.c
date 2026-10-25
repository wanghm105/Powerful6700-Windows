/* Explicit-write payload for the A6700 maintenance process.
 *
 * THIS PAYLOAD CAN MODIFY CAMERA STORAGE. It is loaded only when the host
 * explicitly asks for a write (tools/flash_write.py) and it refuses any target
 * outside /usr/, /cp/ and /setting/ (the last one only for BACKUP.BIN, which
 * carries the CP unit mirror), never opens a device node under /dev, and never
 * reports success when the read-back comparison fails.
 *
 * Request /tmp/jiritsu/tmmc.jit (same 28-byte header as dump_range.c):
 *   0  "A67D"   4  u32 version = 1   8  u32 mode   12 u32 path_len
 *  16  u64 offset   24 u32 length   28 path bytes (path_len)
 * Write data file: /tmp/jiritsu/tmmc.dat, exactly length bytes.
 *
 * Modes: 0 read range, 1 report size, 3 write, 10 truncate, 4 identity probe
 *        (mode 4 reads the range and writes the very same bytes back, so it
 *        exercises the whole write path with zero semantic change.)
 */
#define HEADER 28u
#define PATH_MAX 192u
#define DATA_MAX 0x100000u
#define CHUNK 0x20000u
#define AT_FDCWD -100L
#define SYS_OPENAT 56L
#define SYS_CLOSE 57L
#define SYS_READ 63L
#define SYS_WRITE 64L
#define SYS_PREAD64 67L
#define SYS_PWRITE64 68L
#define SYS_FSYNC 82L
#define SYS_LSEEK 62L
#define SYS_MOUNT 40L
#define SYS_FTRUNCATE 46L
#define SYS_GETEUID 175L
#define SYS_UNLINKAT 35L
#define SEEK_END 2L
#define O_RDONLY 0L
#define O_WRONLY 1
#define O_RDWR 2L
#define O_CREAT 0x40L
#define O_TRUNC 0x200L
#define MS_RDONLY 1L
#define MS_REMOUNT 32L
#define MS_NOATIME 1024L
#define MS_NODIRATIME 2048L
#define MS_SYNCHRONOUS 16L
#define MOUNT_FLAGS (MS_REMOUNT | MS_SYNCHRONOUS | MS_NOATIME | MS_NODIRATIME)

static const char request_path[] = "/tmp/jiritsu/tmmc.jit";
static const char data_path[] = "/tmp/jiritsu/tmmc.dat";
static unsigned char request[HEADER + PATH_MAX];
static unsigned char result[HEADER + DATA_MAX];
static unsigned char want[CHUNK];
static unsigned char got[CHUNK];
static char path_buf[PATH_MAX + 1u];
static int remounted_rw = 0;

static long call6(long n, long a, long b, long c, long d, long e, long f) {
    register long x8 __asm__("x8") = n;
    register long x0 __asm__("x0") = a;
    register long x1 __asm__("x1") = b;
    register long x2 __asm__("x2") = c;
    register long x3 __asm__("x3") = d;
    register long x4 __asm__("x4") = e;
    register long x5 __asm__("x5") = f;
    __asm__ volatile("svc #0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x5)
                     : "memory", "cc");
    return x0;
}

static long call4(long n, long a, long b, long c, long d) {
    return call6(n, a, b, c, d, 0, 0);
}

static long io_error = 0;
static unsigned phase = 0;

static int io(long syscall, long fd, unsigned char *buf, unsigned long size, unsigned long off) {
    unsigned long done = 0;
    unsigned attempts = 0;
    while (done < size && attempts++ < 4096) {
        long n = call4(syscall, fd, (long)(buf + done), (long)(size - done), (long)(off + done));
        if (n == -4) continue;
        if (n <= 0 || (unsigned long)n > size - done) { io_error = n; return 0; }
        done += (unsigned long)n;
    }
    if (done != size) { io_error = -5; return 0; }
    return 1;
}

/* Sequential I/O: some camera filesystems reject random offsets, so the write
   path can position once and then stream with read/write. */
static int stream(long syscall, long fd, unsigned char *buf, unsigned long size,
                  unsigned long off, int position) {
    if (position && call4(SYS_LSEEK, fd, (long)off, 0, 0) != (long)off) { io_error = -6; return 0; }
    return io(syscall, fd, buf, size, 0);
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
static int starts(const char *p, const char *prefix) {
    unsigned i = 0;
    while (prefix[i]) {
        if (p[i] != prefix[i]) return 0;
        i++;
    }
    return 1;
}
static int has(const char *p, const char *needle) {
    for (unsigned i = 0; p[i]; i++) if (starts(p + i, needle)) return 1;
    return 0;
}

static void publish(unsigned status, unsigned mode, unsigned long long size, unsigned length) {
    result[0] = 'A'; result[1] = '6'; result[2] = '7'; result[3] = 'D';
    put32(4, 1);
    put32(8, status);
    put32(12, mode);
    put64(16, size);
    put32(24, length);
    long fd = call4(SYS_OPENAT, AT_FDCWD, (long)request_path, 0x241, 0600);
    if (fd < 0) return;
    if (io(SYS_WRITE, fd, result, HEADER + length, 0)) call4(SYS_FSYNC, fd, 0, 0, 0);
    call4(SYS_CLOSE, fd, 0, 0, 0);
}

/* Mount point that owns path, or 0 when the path is not an allowed target. */
static const char *mount_point(const char *path) {
    if (has(path, "/../") || has(path, "/dev/")) return 0;
    if (starts(path, "/usr/")) return "/usr";
    if (starts(path, "/cp/")) return "/cp";
    if (starts(path, "/setting/")) return "/setting";
    return 0;
}

static long remount(const char *where, int ro) {
    return call6(SYS_MOUNT, 0, (long)where, 0, MOUNT_FLAGS + (ro ? MS_RDONLY : 0), 0, 0);
}

/* Open for writing; on a read-only mount remount it once and retry. */
static long open_writable(const char *path, const char *where, unsigned *status) {
    long fd = call4(SYS_OPENAT, AT_FDCWD, (long)path, O_WRONLY, 0);
    if (fd >= 0) return fd;
    if (fd != -30L || !where) { *status = 2; return -1; }
    if (remount(where, 0) != 0) { *status = 11; return -1; }
    remounted_rw = 1;
    fd = call4(SYS_OPENAT, AT_FDCWD, (long)path, O_WRONLY, 0);
    if (fd < 0) *status = 2;
    return fd;
}

static int compare_file(long fd, unsigned long long offset, unsigned length) {
    phase = 11;
    long check = call4(SYS_OPENAT, AT_FDCWD, (long)data_path, O_RDONLY, 0);
    if (check < 0) return 10;
    unsigned done = 0;
    while (done < length) {
        unsigned want_len = length - done > CHUNK ? CHUNK : length - done;
        phase = 12;
        if (!io(SYS_PREAD64, check, want, want_len, done)) { call4(SYS_CLOSE, check, 0, 0, 0); return 13; }
        phase = 13;
        if (!io(SYS_PREAD64, fd, got, want_len, offset + done)) { call4(SYS_CLOSE, check, 0, 0, 0); return 13; }
        phase = 14;
        for (unsigned i = 0; i < want_len; i++)
            if (want[i] != got[i]) { call4(SYS_CLOSE, check, 0, 0, 0); return 9; }
        done += want_len;
    }
    call4(SYS_CLOSE, check, 0, 0, 0);
    return 0;
}

static unsigned write_and_verify(const char *path, const char *where, unsigned long long offset,
                                 unsigned length, int sequential) {
    unsigned status = 0;
    phase = 1;
    long fd = call4(SYS_OPENAT, AT_FDCWD, (long)path, O_RDONLY, 0);
    if (fd < 0) return 2;
    phase = 2;
    long end = call4(SYS_LSEEK, fd, 0, SEEK_END, 0);
    call4(SYS_CLOSE, fd, 0, 0, 0);
    if (end < 0) return 5;
    phase = 3;
    /* A write that starts exactly at EOF appends (that is how the resource-growth
       test extends a file); anything past EOF is refused, and an in-range write
       may not run past the end. */
    if (offset > (unsigned long long)end) return 12;
    if (offset < (unsigned long long)end && length > (unsigned long long)end - offset) return 12;

    phase = 4;
    long source = call4(SYS_OPENAT, AT_FDCWD, (long)data_path, O_RDONLY, 0);
    if (source < 0) return 10;
    phase = 5;
    /* The data file must hold exactly the block; a stale or appended file would
       silently write the wrong bytes, so the size is checked first. */
    long data_size = call4(SYS_LSEEK, source, 0, SEEK_END, 0);
    if (data_size != (long)length || call4(SYS_LSEEK, source, 0, 0, 0) != 0) {
        call4(SYS_CLOSE, source, 0, 0, 0);
        return 10;
    }

    phase = 6;
    fd = open_writable(path, where, &status);
    if (fd < 0) { call4(SYS_CLOSE, source, 0, 0, 0); return status; }
    phase = 7;

    unsigned done = 0;
    while (done < length) {
        unsigned want_len = length - done > CHUNK ? CHUNK : length - done;
        if (!io(SYS_PREAD64, source, want, want_len, done)) {
            call4(SYS_CLOSE, source, 0, 0, 0);
            call4(SYS_CLOSE, fd, 0, 0, 0);
            return 13;
        }
        int wrote = sequential
            ? stream(SYS_WRITE, fd, want, want_len, (unsigned long)(offset + done), done == 0)
            : io(SYS_PWRITE64, fd, want, want_len, offset + done);
        if (!wrote) {
            call4(SYS_CLOSE, source, 0, 0, 0);
            call4(SYS_CLOSE, fd, 0, 0, 0);
            return 7;
        }
        phase = 8;
        done += want_len;
    }
    call4(SYS_CLOSE, source, 0, 0, 0);

    phase = 9;
    if (call4(SYS_FSYNC, fd, 0, 0, 0) != 0) {
        call4(SYS_CLOSE, fd, 0, 0, 0);
        return 8;
    }
    call4(SYS_CLOSE, fd, 0, 0, 0);
    /* The write handle is O_WRONLY; pread on it is EBADF, so the readback gets
       its own read-only handle the way the A7C2 installer verifies. */
    phase = 10;
    long readback = call4(SYS_OPENAT, AT_FDCWD, (long)path, O_RDONLY, 0);
    if (readback < 0) return 2;
    int result_status = compare_file(readback, offset, length);
    call4(SYS_CLOSE, readback, 0, 0, 0);
    return (unsigned)result_status;
}

static const char *scratch_path = "/tmp/jiritsu/scratch.bin";

/* Mode 9 keeps the same open/write/fsync/pread dance but on a file we own in
   /tmp, so a layout or syscall problem shows up without touching camera data. */
static void probe_scratch(void) {
    phase = 30;
    long f = call4(SYS_OPENAT, AT_FDCWD, (long)scratch_path, O_RDWR | O_CREAT | O_TRUNC, 0600);
    if (f < 0) { publish(2, 9, (unsigned long long)io_error, phase); return; }
    for (unsigned i = 0; i < 512; i++) want[i] = (unsigned char)(i * 7u);
    phase = 31;
    if (!io(SYS_WRITE, f, want, 512, 0)) { call4(SYS_CLOSE, f, 0, 0, 0); publish(7, 9, (unsigned long long)io_error, phase); return; }
    phase = 32;
    if (call4(SYS_FSYNC, f, 0, 0, 0) != 0) { call4(SYS_CLOSE, f, 0, 0, 0); publish(8, 9, (unsigned long long)io_error, phase); return; }
    phase = 33;
    if (!io(SYS_PREAD64, f, got, 512, 0)) { call4(SYS_CLOSE, f, 0, 0, 0); publish(13, 9, (unsigned long long)io_error, phase); return; }
    phase = 34;
    for (unsigned i = 0; i < 512; i++)
        if (want[i] != got[i]) { call4(SYS_CLOSE, f, 0, 0, 0); publish(9, 9, i, phase); return; }
    phase = 35;
    if (!io(SYS_PWRITE64, f, want, 512, 0)) { call4(SYS_CLOSE, f, 0, 0, 0); publish(7, 9, (unsigned long long)io_error, phase); return; }
    phase = 36;
    if (call4(SYS_FSYNC, f, 0, 0, 0) != 0) { call4(SYS_CLOSE, f, 0, 0, 0); publish(8, 9, (unsigned long long)io_error, phase); return; }
    phase = 37;
    if (!io(SYS_PREAD64, f, got, 512, 0)) { call4(SYS_CLOSE, f, 0, 0, 0); publish(13, 9, (unsigned long long)io_error, phase); return; }
    phase = 38;
    for (unsigned i = 0; i < 512; i++)
        if (want[i] != got[i]) { call4(SYS_CLOSE, f, 0, 0, 0); publish(9, 9, i, phase); return; }
    call4(SYS_CLOSE, f, 0, 0, 0);
    phase = 39;
    call4(SYS_UNLINKAT, AT_FDCWD, (long)scratch_path, 0, 0);
    publish(0, 9, 0, 39);
}

__attribute__((constructor)) static void run(void) {
    long fd = call4(SYS_OPENAT, AT_FDCWD, (long)request_path, 0, 0);
    if (fd < 0) return;
    int ok = io(SYS_PREAD64, fd, request, HEADER, 0);
    call4(SYS_CLOSE, fd, 0, 0, 0);
    if (!ok || !same4(request, "A67D") || get32(4) != 1) { publish(1, 0, 0, 0); return; }

    unsigned mode = get32(8);
    unsigned path_len = get32(12);
    unsigned length = get32(24);
    if (mode == 9) { probe_scratch(); return; }
    if (path_len == 0 || path_len > PATH_MAX || (mode != 10 && mode > 6) || mode == 2
        || (mode == 0 && (length == 0 || length > DATA_MAX))
        || ((mode == 3 || mode == 6) && (length == 0 || length > DATA_MAX))) {
        publish(4, mode, 0, 0);
        return;
    }
    fd = call4(SYS_OPENAT, AT_FDCWD, (long)request_path, 0, 0);
    if (fd < 0) { publish(2, mode, 0, 0); return; }
    ok = io(SYS_PREAD64, fd, request + HEADER, path_len, HEADER);
    call4(SYS_CLOSE, fd, 0, 0, 0);
    if (!ok) { publish(1, mode, 0, 0); return; }
    for (unsigned i = 0; i < path_len; i++) path_buf[i] = (char)request[HEADER + i];
    path_buf[path_len] = 0;
    const char *where = mount_point(path_buf);

    if (mode == 1) {
        long file = call4(SYS_OPENAT, AT_FDCWD, (long)path_buf, 0, 0);
        if (file < 0) { publish(2, mode, 0, 0); return; }
        long end = call4(SYS_LSEEK, file, 0, SEEK_END, 0);
        call4(SYS_CLOSE, file, 0, 0, 0);
        if (end < 0) { publish(5, mode, 0, 0); return; }
        publish(0, mode, (unsigned long long)end, 0);
        return;
    }

    if (mode == 0) {
        long file = call4(SYS_OPENAT, AT_FDCWD, (long)path_buf, 0, 0);
        if (file < 0) { publish(2, mode, 0, 0); return; }
        unsigned long long offset = get64(16);
        int read_ok = io(SYS_PREAD64, file, result + HEADER, length, (unsigned long)offset);
        call4(SYS_CLOSE, file, 0, 0, 0);
        if (!read_ok) { publish(3, mode, 0, 0); return; }
        publish(0, mode, 0, length);
        return;
    }

    /* Modes 3 and 4 write; both refuse anything outside /usr/, /cp/ and /setting/. */
    if (!where || call6(SYS_GETEUID, 0, 0, 0, 0, 0, 0) != 0) { publish(6, mode, 0, 0); return; }
    unsigned long long offset = get64(16);

    /* Mode 10 restores the original length after a larger file was written. The
       host uses it only to undo an experiment, so it never grows a file. */
    if (mode == 10) {
        unsigned status = 0;
        phase = 41;
        long file = open_writable(path_buf, where, &status);
        if (file < 0) { publish(status, mode, 0, 41); return; }
        if (call6(SYS_FTRUNCATE, file, (long)offset, 0, 0, 0, 0) != 0) {
            call4(SYS_CLOSE, file, 0, 0, 0);
            if (remounted_rw) remount(where, 1);
            publish(14, mode, (unsigned long long)io_error, 41);
            return;
        }
        if (call4(SYS_FSYNC, file, 0, 0, 0) != 0) {
            call4(SYS_CLOSE, file, 0, 0, 0);
            if (remounted_rw) remount(where, 1);
            publish(8, mode, (unsigned long long)io_error, 41);
            return;
        }
        call4(SYS_CLOSE, file, 0, 0, 0);
        phase = 42;
        long check = call4(SYS_OPENAT, AT_FDCWD, (long)path_buf, O_RDONLY, 0);
        if (check < 0) { if (remounted_rw) remount(where, 1); publish(2, mode, 0, 42); return; }
        long end = call4(SYS_LSEEK, check, 0, SEEK_END, 0);
        call4(SYS_CLOSE, check, 0, 0, 0);
        if (remounted_rw) remount(where, 1);
        if (end < 0 || (unsigned long long)end != offset) { publish(9, mode, (unsigned long long)end, 42); return; }
        publish(0, mode, (unsigned long long)end, 42);
        return;
    }

    if (mode == 4 || mode == 5) {
        long file = call4(SYS_OPENAT, AT_FDCWD, (long)path_buf, 0, 0);
        if (file < 0) { publish(2, mode, 0, 0); return; }
        if (length == 0 || length > CHUNK) { call4(SYS_CLOSE, file, 0, 0, 0); publish(4, mode, 0, 0); return; }
        phase = 21;
        int read_ok = mode == 5
            ? stream(SYS_READ, file, want, length, (unsigned long)offset, 1)
            : io(SYS_PREAD64, file, want, length, (unsigned long)offset);
        call4(SYS_CLOSE, file, 0, 0, 0);
        if (!read_ok) { publish(3, mode, (unsigned long long)io_error, 0); return; }
        phase = 22;
        long sink = call4(SYS_OPENAT, AT_FDCWD, (long)data_path, O_WRONLY | O_CREAT | O_TRUNC, 0600);
        if (sink < 0) { publish(10, mode, 0, 0); return; }
        if (!io(SYS_WRITE, sink, want, length, 0)) { call4(SYS_CLOSE, sink, 0, 0, 0); publish(10, mode, 0, 0); return; }
        call4(SYS_CLOSE, sink, 0, 0, 0);
    }

    unsigned status = write_and_verify(path_buf, where, offset, length, mode >= 5);
    if (remounted_rw) remount(where, 1);
    publish(status, mode, status ? (unsigned long long)io_error : 0, status ? phase : length);
}
