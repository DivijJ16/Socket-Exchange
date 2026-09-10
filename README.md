# The Socket Exchange — COL334 Assignment 2

**Team Members:**
- Divij Jain (2024CS50052)
- Tushar (2024CS50554)

---

## 1. Language and Runtime Environment
- **Language:** Python 3 (tested on Python 3.12 under FreeBSD 14-RELEASE on ARM64/x86_64).
- **Dependencies:** Standard library only (`socket`, `select`, `os`, `sys`, `struct`, `time`). No third-party packages or virtual environments are needed.

---

## 2. Build and Preparation
Because the project is written in Python, no compilation or build step is required.

Before running the programs, ensure that all shell launchers have executable permissions:
```bash
chmod +x server/run-server client/run-trader client/run-market-data
```

## 3. How to Start the Exchange Server
Run the launcher script from the root of the repository, providing the host address and listening port:

```bash
./server/run-server <host> <port>
```

Example:

```bash
./server/run-server 127.0.0.1 5000
```

(Alternatively, execute directly via `python3 src/server.py 127.0.0.1 5000`).

## 4. How to Start the Clients

### Trader Client
Launches an interactive trading terminal session with the specified username:

```bash
./client/run-trader <host> <port> <username>
```

Example:

```bash
./client/run-trader 127.0.0.1 5000 alice
```

Supported commands once connected:

* `BUY <instrument> <quantity> <price>`
* `SELL <instrument> <quantity> <price>`
* `CANCEL <order_id>`
* `QUIT`

### Market-Data Client
Launches a read-only client that immediately subscribes to the specified instrument:

```bash
./client/run-market-data <host> <port> <instrument>
```

Example:

```bash
./client/run-market-data 127.0.0.1 5000 JNST
```

Supported commands once connected:

* `SUBSCRIBE <instrument>` (supports `JNST` or `IMCT`)
* `UNSUBSCRIBE <instrument>`
* `QUIT`

## 5. Configuration & Design Notes

* **Multiplexing Architecture:** The Exchange Server relies on FreeBSD's kernel event notification interface (`kqueue`) with non-blocking sockets (`setblocking(False)`) to handle thousands of concurrent client connections without threads.

* **Client I/O:** The Trader and Market-Data clients use `select()` to multiplex stdin reads (`os.read`) alongside incoming TCP socket traffic without deadlocking.

* **Message Framing:** All messages are UTF-8 text delimited by a newline (`\n`). Incoming byte streams are buffered incrementally to handle TCP packet fragmentation and partial transmissions.
