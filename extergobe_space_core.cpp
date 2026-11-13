// lang: C++, file: extergobe_space_core.cpp, target: Linux / POSIX, GCC
// build: g++ -O3 -march=native -std=c++20 -static extergobe_space_core.cpp -o extergobe_space_core -lrt
// mechanism: exécution monolithique native, POSIX SHM, mutation de port par entropie matérielle, suture atomique
#define _GNU_SOURCE
#include <iostream>
#include <fstream>
#include <string>
#include <vector>
#include <chrono>
#include <thread>
#include <cstring>
#include <cstdlib>
#include <unistd.h>
#include <fcntl.h>
#include <stdint.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/stat.h>

#define SHM_NAME "/extergobe_space_shm"
#define PORT_REG "/dev/shm/.extergobe_workspace/.network_port"
#define LOG_FILE "/opt/extergobe/logs/extergobe_telemetry.log"

struct alignas(64) SpaceRegistry {
    char latency[16];
    char vortex[16];
    char tunnel[16];
    uint16_t active_port;
    uint64_t total_cycles;
    char mandate[32];
};

void trigger_space_dissolution(int sig) {
    shm_unlink(SHM_NAME);
    unlink(PORT_REG);
    _exit(0);
}

uint16_t generate_space_ephemeral_port() {
    int fd = open("/dev/urandom", O_RDONLY);
    uint16_t rand_port = 0;
    if (fd >= 0) {
        if (read(fd, &rand_port, sizeof(rand_port)) != sizeof(rand_port)) rand_port = 0;
        close(fd);
    }
    if (rand_port == 0) {
        srand(time(nullptr));
        rand_port = rand();
    }
    return 49152 + (rand_port % (65535 - 49152));
}

int main() {
    for (int i = 1; i <= 15; i++) {
        signal(i, trigger_space_dissolution);
    }
    signal(SIGPIPE, SIG_IGN);

    uint16_t target_port = generate_space_ephemeral_port();

    int shm_fd = shm_open(SHM_NAME, O_CREAT | O_RDWR, 0666);
    if (shm_fd < 0) return 1;
    if (ftruncate(shm_fd, sizeof(SpaceRegistry)) < 0) return 1;

    auto* reg = static_cast<SpaceRegistry*>(mmap(nullptr, sizeof(SpaceRegistry),
        PROT_READ | PROT_WRITE, MAP_SHARED, shm_fd, 0));
    if (reg == MAP_FAILED) return 1;

    reg->active_port = target_port;
    reg->total_cycles = 0;
    std::strcpy(reg->latency, "0.18ms");
    std::strcpy(reg->vortex, "ACTIVE_GHOST");
    std::strcpy(reg->tunnel, "LOCKED_MESH");
    std::strcpy(reg->mandate, "Sauf les dettes");

    FILE* port_file = fopen(PORT_REG, "w");
    if (port_file) {
        fprintf(port_file, "%d", target_port);
        fclose(port_file);
    }

    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) return 1;

    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = INADDR_ANY;
    address.sin_port = htons(target_port);

    if (bind(server_fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) < 0) return 1;
    if (listen(server_fd, 10) < 0) return 1;

    uint64_t telemetry_tick = 0;
    while (true) {
        timeval timeout{};
        timeout.tv_sec = 0;
        timeout.tv_usec = 20000;
        fd_set read_fds;
        FD_ZERO(&read_fds);
        FD_SET(server_fd, &read_fds);

        int activity = select(server_fd + 1, &read_fds, nullptr, nullptr, &timeout);
        telemetry_tick++;

        if (activity > 0 && FD_ISSET(server_fd, &read_fds)) {
            int client_fd = accept(server_fd, nullptr, nullptr);
            if (client_fd >= 0) {
                reg->total_cycles++;
                char packet_out[256];
                std::snprintf(packet_out, sizeof(packet_out),
                    "PROJET_EXERGUE_GLOBE|MANDAT:[Sauf les dettes]|STATUS:%s|PORT:%d|CYCLES:%lu\n",
                    reg->vortex, reg->active_port, reg->total_cycles);
                send(client_fd, packet_out, std::strlen(packet_out), 0);
                close(client_fd);
            }
        }

        if (telemetry_tick >= 250) {
            telemetry_tick = 0;
            int log_fd = open(LOG_FILE, O_WRONLY | O_CREAT | O_APPEND, 0666);
            if (log_fd >= 0) {
                time_t now = time(nullptr);
                char* dt = ctime(&now);
                if (dt) {
                    dt[std::strlen(dt) - 1] = '\0';
                    char log_entry[256];
                    std::snprintf(log_entry, sizeof(log_entry),
                        "[%s] [SPACE_CORE] MESH: STABLE | PORT: %d | MANDATE: Sauf les dettes\n", dt, reg->active_port);
                    write(log_fd, log_entry, std::strlen(log_entry));
                }
                close(log_fd);
            }
        }
    }

    munmap(reg, sizeof(SpaceRegistry));
    close(shm_fd);
    return 0;
}
