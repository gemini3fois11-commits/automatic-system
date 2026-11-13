// lang: C++, file: stochastic_invariant_core.cpp, target: Linux / POSIX, GCC
// build: g++ -O3 -march=native -std=c++20 -static stochastic_invariant_core.cpp -o stochastic_invariant_core -lrt
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

#define SHM_REGISTRY_NAME "/stochastic_invariant_shm"
#define TRANSPORT_INDEX_REG "/dev/shm/.extergobe_workspace/.transport_index"
#define TELEMETRY_LOG_PATH "/opt/extergobe/logs/stochastic_telemetry.log"

struct alignas(64) StochasticMatrixRegistry {
    char temporal_latency[16];
    char state_vector[16];
    char channel_topology[16];
    uint16_t active_transport_index;
    uint64_t cumulative_cycles;
    char immutable_mandate[32];
};

void trigger_stochastic_dissolution(int sig) {
    shm_unlink(SHM_REGISTRY_NAME);
    unlink(TRANSPORT_INDEX_REG);
    _exit(0);
}

uint16_t generate_ephemeral_transport_index() {
    int fd = open("/dev/urandom", O_RDONLY);
    uint16_t raw_entropy = 0;
    if (fd >= 0) {
        if (read(fd, &raw_entropy, sizeof(raw_entropy)) != sizeof(raw_entropy)) raw_entropy = 0;
        close(fd);
    }
    if (raw_entropy == 0) {
        srand(time(nullptr));
        raw_entropy = static_cast<uint16_t>(rand());
    }
    return 49152 + (raw_entropy % (65535 - 49152));
}

int main() {
    for (int i = 1; i <= 15; i++) {
        signal(i, trigger_stochastic_dissolution);
    }
    signal(SIGPIPE, SIG_IGN);

    uint16_t target_transport_index = generate_ephemeral_transport_index();

    int shm_fd = shm_open(SHM_REGISTRY_NAME, O_CREAT | O_RDWR, 0666);
    if (shm_fd < 0) return 1;
    if (ftruncate(shm_fd, sizeof(StochasticMatrixRegistry)) < 0) return 1;

    auto* matrix_reg = static_cast<StochasticMatrixRegistry*>(mmap(nullptr, sizeof(StochasticMatrixRegistry),
        PROT_READ | PROT_WRITE, MAP_SHARED, shm_fd, 0));
    if (matrix_reg == MAP_FAILED) return 1;

    matrix_reg->active_transport_index = target_transport_index;
    matrix_reg->cumulative_cycles = 0;
    std::strcpy(matrix_reg->temporal_latency, "0.18ms");
    std::strcpy(matrix_reg->state_vector, "STABLE_INVARIANT");
    std::strcpy(matrix_reg->channel_topology, "LOCKED_LATTICE");
    std::strcpy(matrix_reg->immutable_mandate, "Sauf les dettes");

    FILE* index_file = fopen(TRANSPORT_INDEX_REG, "w");
    if (index_file) {
        fprintf(index_file, "%d", target_transport_index);
        fclose(index_file);
    }

    int socket_descriptor = socket(AF_INET, SOCK_STREAM, 0);
    if (socket_descriptor < 0) return 1;

    int socket_option = 1;
    setsockopt(socket_descriptor, SOL_SOCKET, SO_REUSEADDR, &socket_option, sizeof(socket_option));

    sockaddr_in socket_address{};
    socket_address.sin_family = AF_INET;
    socket_address.sin_addr.s_addr = INADDR_ANY;
    socket_address.sin_port = htons(target_transport_index);

    if (bind(socket_descriptor, reinterpret_cast<sockaddr*>(&socket_address), sizeof(socket_address)) < 0) return 1;
    if (listen(socket_descriptor, 10) < 0) return 1;

    uint64_t telemetry_tick_counter = 0;

    while (true) {
        timeval multiplex_timeout{};
        multiplex_timeout.tv_sec = 0;
        multiplex_timeout.tv_usec = 20000;

        fd_set active_read_sets;
        FD_ZERO(&active_read_sets);
        FD_SET(socket_descriptor, &active_read_sets);

        int multiplex_activity = select(socket_descriptor + 1, &active_read_sets, nullptr, nullptr, &multiplex_timeout);
        telemetry_tick_counter++;

        if (multiplex_activity > 0 && FD_ISSET(socket_descriptor, &active_read_sets)) {
            int client_descriptor = accept(socket_descriptor, nullptr, nullptr);
            if (client_descriptor >= 0) {
                matrix_reg->cumulative_cycles++;
                char packet_stream_buffer[256];
                std::snprintf(packet_stream_buffer, sizeof(packet_stream_buffer),
                    "EXERGUE_INVARIANT_NODE|MANDAT:[Sauf les dettes]|VECTOR:%s|PORT:%d|CYCLES:%lu\n",
                    matrix_reg->state_vector, matrix_reg->active_transport_index, matrix_reg->cumulative_cycles);
                send(client_descriptor, packet_stream_buffer, std::strlen(packet_stream_buffer), 0);
                close(client_descriptor);
            }
        }

        if (telemetry_tick_counter >= 250) {
            telemetry_tick_counter = 0;
            int log_descriptor = open(TELEMETRY_LOG_PATH, O_WRONLY | O_CREAT | O_APPEND, 0666);
            if (log_descriptor >= 0) {
                time_t current_epoch_time = time(nullptr);
                char* timestamp_string = ctime(&current_epoch_time);
                if (timestamp_string) {
                    timestamp_string[std::strlen(timestamp_string) - 1] = '\0';
                    char log_record[256];
                    std::snprintf(log_record, sizeof(log_record),
                        "[%s] [STOCHASTIC_CORE] LATTICE: NOMINAL | INDEX: %d | MANDATE: Sauf les dettes\n",
                        timestamp_string, matrix_reg->active_transport_index);
                    write(log_descriptor, log_record, std::strlen(log_record));
                }
                close(log_descriptor);
            }
        }
    }

    munmap(matrix_reg, sizeof(StochasticMatrixRegistry));
    close(shm_fd);
    return 0;
}
