/* Fixed-profile AArch64 Linux constructor, no libc or arbitrary device API.
 * BUILD_WRITER=0 reads only the supported sparse entries.
 * BUILD_WRITER=1 checks ALL preimages before writing catalog-owned bytes,
 * then checks every write/fsync/readback and rolls attempted sectors back on
 * failure. A lost USB response never causes the host to resend a writer.
 * Linux asm-generic syscall ABI: fsync=82 (74 is signalfd4).
 */
#include "profile.h"

#define HEADER 56u
#define REPLY 44u
#define AT_FDCWD -100L
#define SYS_OPENAT 56L
#define SYS_CLOSE 57L
#define SYS_READ 63L
#define SYS_WRITE 64L
#define SYS_PREAD64 67L
#define SYS_PWRITE64 68L
#define SYS_FSYNC 82L

static long call4(long n, long a, long b, long c, long d) {
    register long x8 __asm__("x8")=n;
    register long x0 __asm__("x0")=a;
    register long x1 __asm__("x1")=b;
    register long x2 __asm__("x2")=c;
    register long x3 __asm__("x3")=d;
    __asm__ volatile("svc #0" : "+r"(x0) : "r"(x8),"r"(x1),"r"(x2),"r"(x3) : "memory");
    return x0;
}
static unsigned char input[HEADER + ENTRY_COUNT * 1024u];
static unsigned char output[REPLY + ENTRY_COUNT * 512u];
static unsigned char touched[ENTRY_COUNT];
static const char result_path[]="/tmp/jiritsu/tmmc.jit";
static const char *const devices[]={"/dev/nflasha15","/dev/nflasha5","/dev/nflasha8"};
#define DEVICE_COUNT 3u
static int same(const unsigned char *a,const unsigned char *b,unsigned long n) {
    for(unsigned long i=0;i<n;i++) if(a[i]!=b[i]) return 0;
    return 1;
}
static void put32(unsigned off,unsigned value) {
    for(unsigned i=0;i<4;i++) output[off+i]=(unsigned char)(value>>(8*i));
}
static unsigned get32(unsigned off) {
    return (unsigned)input[off]|((unsigned)input[off+1]<<8)|((unsigned)input[off+2]<<16)|((unsigned)input[off+3]<<24);
}
/* Bound EINTR/short-I/O retries; zero-length progress is always a failure. */
static int io(long syscall,long fd,unsigned char *buf,unsigned long size,unsigned long off) {
    unsigned long done=0;
    unsigned attempts=0;
    while(done<size && attempts++<1024) {
        long n=call4(syscall,fd,(long)(buf+done),(long)(size-done),(long)(off+done));
        if(n==-4) continue;
        if(n<=0 || (unsigned long)n>size-done) return 0;
        done+=(unsigned long)n;
    }
    return done==size;
}
static int sync_fd(long fd) {
    for(unsigned i=0;i<16;i++) {
        long rc=call4(SYS_FSYNC,fd,0,0,0);
        if(rc==0) return 1;
        if(rc!=-4) break;
    }
    return 0;
}
static int read_request(unsigned size) {
    long fd=call4(SYS_OPENAT,AT_FDCWD,(long)result_path,0,0);
    if(fd<0) return 0;
    int ok=io(SYS_READ,fd,input,size,0);
    unsigned char extra;
    if(ok && call4(SYS_READ,fd,(long)&extra,1,0)!=0) ok=0;
    call4(SYS_CLOSE,fd,0,0,0);
    return ok;
}
static void finish(unsigned status,unsigned count,unsigned failed,unsigned written,unsigned flags) {
    output[0]='A';output[1]='6';output[2]='7';output[3]='R';
    put32(4,1);
    for(unsigned i=0;i<16;i++) output[8+i]=input[8+i];
    put32(24,status);put32(28,count);put32(32,failed);put32(36,written);put32(40,flags);
    long fd=call4(SYS_OPENAT,AT_FDCWD,(long)result_path,0x241,0600);
    if(fd>=0) {
        if(io(SYS_WRITE,fd,output,REPLY+count*512u,0)) sync_fd(fd);
        call4(SYS_CLOSE,fd,0,0,0);
    }
}
__attribute__((constructor)) static void run(void) {
    const unsigned request_size=HEADER+(BUILD_WRITER ? ENTRY_COUNT*1024u : 0u);
    unsigned status=0,failed=0xffffffffu,written=0,flags=0;
    long fds[DEVICE_COUNT]={-1,-1,-1};
    unsigned char buf[512];
    if(!read_request(request_size) || !same(input,(const unsigned char *)(BUILD_WRITER ? "A67W":"A67Q"),4)
       || get32(4)!=1 || !same(input+24,PROFILE_DIGEST,32)) {
        finish(2,0,failed,0,0);return;
    }
    for(unsigned d=0;d<DEVICE_COUNT;d++) {
        fds[d]=call4(SYS_OPENAT,AT_FDCWD,(long)devices[d],BUILD_WRITER ? 2:0,0);
        if(fds[d]<0) { status=3;goto done; }
    }
    /* First pass validates every target AND every read-only layout guard. */
    for(unsigned i=0;i<ENTRY_COUNT;i++) {
        const struct Entry *e=&ENTRIES[i];
        if(!io(SYS_PREAD64,fds[e->device],buf,512,e->offset)) { status=4;failed=i;goto done; }
        if(!BUILD_WRITER) {
            for(unsigned j=0;j<512;j++) output[REPLY+i*512u+j]=buf[j];
        } else {
            const unsigned char *before=input+HEADER+i*1024u,*after=before+512;
            if(!same(buf,before,512)) { status=1;failed=i;goto done; }
            for(unsigned j=0;j<512;j++) {
                if(before[j]!=after[j] && !(e->mask[j/8] & (1u<<(j%8)))) {
                    status=2;failed=i;goto done;
                }
            }
        }
    }
    if(BUILD_WRITER) for(unsigned i=0;i<ENTRY_COUNT;i++) {
        const struct Entry *e=&ENTRIES[i];
        unsigned char *before=input+HEADER+i*1024u,*after=before+512;
        if(same(before,after,512)) continue;
        /* Recheck immediately before this write as well as the first pass. */
        if(!io(SYS_PREAD64,fds[e->device],buf,512,e->offset)) { status=4;failed=i;goto rollback; }
        if(!same(buf,before,512)) { status=1;failed=i;goto rollback; }
        touched[i]=1;written++;
        if(!io(SYS_PWRITE64,fds[e->device],after,512,e->offset)) { status=5;failed=i;goto rollback; }
        if(!sync_fd(fds[e->device])) { status=6;failed=i;goto rollback; }
        if(!io(SYS_PREAD64,fds[e->device],buf,512,e->offset) || !same(buf,after,512)) {
            status=7;failed=i;goto rollback;
        }
    }
    goto done;
rollback:
    if(written) {
        int ok=1;
        for(unsigned k=ENTRY_COUNT;k>0;k--) {
            unsigned i=k-1;
            if(!touched[i]) continue;
            const struct Entry *e=&ENTRIES[i];
            unsigned char *before=input+HEADER+i*1024u;
            if(!io(SYS_PWRITE64,fds[e->device],before,512,e->offset) || !sync_fd(fds[e->device])
               || !io(SYS_PREAD64,fds[e->device],buf,512,e->offset) || !same(buf,before,512)) ok=0;
        }
        if(ok) flags=1; else status=8;
    }
done:
    for(unsigned d=0;d<DEVICE_COUNT;d++) if(fds[d]>=0) call4(SYS_CLOSE,fds[d],0,0,0);
    finish(status,BUILD_WRITER ? 0:ENTRY_COUNT,failed,written,flags);
}
