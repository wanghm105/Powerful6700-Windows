/* Capture one Sony MSC camera for libusb. No automatic USB reset,
   driver-presence prerequisite or storage-volume prerequisite. */
#import <Foundation/Foundation.h>
#import <IOUSBHost/IOUSBHost.h>
#import <IOKit/IOKitLib.h>
#include <stdio.h>
#include <unistd.h>

static BOOL hasMassStorage(io_service_t service) {
    io_iterator_t children = 0;
    if (IORegistryEntryCreateIterator(service, kIOServicePlane, kIORegistryIterateRecursively,
                                      &children) != KERN_SUCCESS) return NO;
    BOOL found = NO;
    io_registry_entry_t child;
    while ((child = IOIteratorNext(children))) {
        if (IOObjectConformsTo(child, "IOUSBMassStorageDriver") || IOObjectConformsTo(child, "IOMedia")) {
            found = YES;
        }
        IOObjectRelease(child);
    }
    IOObjectRelease(children);
    return found;
}

/* USB identity/descriptors establish MSC even after a previous surrender has
   removed the storage driver or when no SD card/volume is mounted. */
static BOOL isMSC(io_service_t service, uint16_t product) {
    if (product == 0x0e76 || product == 0x047d) return YES;
    io_iterator_t children = 0;
    if (IORegistryEntryCreateIterator(service, kIOServicePlane, kIORegistryIterateRecursively,
                                      &children) != KERN_SUCCESS) return NO;
    BOOL found = NO;
    io_registry_entry_t child;
    while ((child = IOIteratorNext(children))) {
        if (IOObjectConformsTo(child, "IOUSBHostInterface")) {
            CFTypeRef cls = IORegistryEntryCreateCFProperty(child, CFSTR("bInterfaceClass"), kCFAllocatorDefault, 0);
            int number = 0;
            if (cls && CFGetTypeID(cls) == CFNumberGetTypeID()) CFNumberGetValue(cls, kCFNumberIntType, &number);
            if (number == 0x08) found = YES;
            if (cls) CFRelease(cls);
        }
        IOObjectRelease(child);
    }
    IOObjectRelease(children);
    return found;
}

/* Return a retained service for exactly one physical Sony MSC camera. During re-enumeration macOS can expose several IOService nodes for
   the same port; deduplicate by locationID and prefer the node that already
   has a mass-storage driver. Different ports still count as different cameras. */
static uint64_t cameraLocation(io_service_t service) {
    uint64_t value = 0;
    CFTypeRef loc = IORegistryEntryCreateCFProperty(service, CFSTR("locationID"), kCFAllocatorDefault, 0);
    if (loc) {
        CFNumberGetValue(loc, kCFNumberSInt64Type, &value);
        CFRelease(loc);
    }
    if (value == 0) {
        CFTypeRef addr = IORegistryEntryCreateCFProperty(service, CFSTR("USB Address"), kCFAllocatorDefault, 0);
        if (addr) {
            CFNumberGetValue(addr, kCFNumberSInt64Type, &value);
            CFRelease(addr);
        }
    }
    if (value == 0) IORegistryEntryGetRegistryEntryID(service, &value);
    return value;
}

static io_service_t findCamera(void) {
    io_iterator_t iter = 0;
    IOServiceGetMatchingServices(kIOMainPortDefault, IOServiceMatching("IOUSBHostDevice"), &iter);
    io_service_t svc = 0, cur;
    uint64_t chosen = 0;
    unsigned unique = 0;
    BOOL chosenHasStorage = NO;
    while ((cur = IOIteratorNext(iter))) {
        CFTypeRef v = IORegistryEntryCreateCFProperty(cur, CFSTR("idVendor"), kCFAllocatorDefault, 0);
        uint16_t vv = 0; if (v) { CFNumberGetValue(v, kCFNumberSInt16Type, &vv); CFRelease(v); }
        CFTypeRef p = IORegistryEntryCreateCFProperty(cur, CFSTR("idProduct"), kCFAllocatorDefault, 0);
        uint16_t pp = 0; if (p) { CFNumberGetValue(p, kCFNumberSInt16Type, &pp); CFRelease(p); }
        if (vv != 0x054c || !isMSC(cur, pp)) { IOObjectRelease(cur); continue; }
        uint64_t loc = cameraLocation(cur);
        if (unique == 0) {
            svc = cur; chosen = loc; unique = 1; chosenHasStorage = hasMassStorage(cur);
            continue;
        }
        if (loc == chosen) {
            BOOL hasStorage = hasMassStorage(cur);
            if (!chosenHasStorage && hasStorage) {
                IOObjectRelease(svc);
                svc = cur; chosenHasStorage = YES;
            } else {
                IOObjectRelease(cur);
            }
            continue;
        }
        unique++;
        IOObjectRelease(cur);
    }
    IOObjectRelease(iter);
    if (unique != 1) {
        if (svc) IOObjectRelease(svc);
        return 0;
    }
    return svc;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        if (argc != 1) { printf("unsupported option; automatic USB reset is disabled\n"); return 2; }
        if (geteuid() != 0) { printf("need root\n"); return 9; }
        io_service_t svc = findCamera();
        if (!svc) { printf("need exactly one Sony MSC camera\n"); return 1; }
        dispatch_queue_t q = dispatch_queue_create("t", NULL);
        NSError *err = nil;
        IOUSBHostDevice *dev = [[IOUSBHostDevice alloc] initWithIOService:svc
            options:IOUSBHostObjectInitOptionsDeviceCapture queue:q error:&err interestHandler:nil];
        printf("capture: %s %s\n", dev ? "OK" : "FAIL", dev ? "" : err.description.UTF8String);
        if (!dev) { IOObjectRelease(svc); return 2; }
        sleep(1);
        [dev destroyWithOptions:IOUSBHostObjectDestroyOptionsDeviceSurrender];
        printf("surrendered\n");
        IOObjectRelease(svc);
    }
    return 0;
}
