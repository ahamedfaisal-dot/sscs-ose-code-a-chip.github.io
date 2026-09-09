# OpenNTT: Unified, Reconfigurable, Side-Channel-Aware Post-Quantum Cryptography Accelerator

**OpenNTT** is an open-source hardware accelerator for the Number Theoretic Transform (NTT) — the computational bottleneck in the NIST Post-Quantum Cryptography (PQC) standards **ML-KEM (Kyber)** and **ML-DSA (Dilithium)**.

It is tightly coupled to a **RISC-V (PicoRV32)** core as a custom-instruction, self-DMA capable coprocessor and prepared for fabrication on the **SkyWater 130nm (Sky130)** open-source PDK.

---

## 1. Overview in Plain English

### The Quantum Threat & Post-Quantum Cryptography
Today's public-key cryptography (RSA, ECC) will be rendered insecure once large-scale quantum computers arrive. In 2024, NIST released the official Post-Quantum Cryptography (PQC) lattice standards:
* **ML-KEM (Kyber)**: Post-quantum key encapsulation and encryption.
* **ML-DSA (Dilithium)**: Post-quantum digital signatures.

### The Problem
Over 80% to 90% of the runtime in these quantum-proof algorithms is spent multiplying giant polynomials with hundreds of coefficients. Doing this directly on standard embedded CPUs requires tens of thousands of modular multiplications, creating a severe bottleneck for low-power and IoT devices.

### The Solution: OpenNTT
OpenNTT offloads the entire polynomial multiplication pipeline from software into dedicated hardware. Instead of performing thousands of instructions, the host CPU issues a single custom instruction (`custom0`). OpenNTT fetches the data directly from shared system memory via self-DMA, performs the complete transform in silicon, and alerts the CPU when complete.

---

## 2. Key Architectural Innovations

| # | Novel Feature | Technical Summary | Impact / Benefit |
|---|---|---|---|
| **N1** | **Unified Poly-Mult Engine** | Single datapath executes Forward NTT, Inverse NTT (INTT), Point-Wise Multiplication (PWM), and Domain Scaling without CPU intervention. | Eliminates software-hardware round-trips for intermediate steps; verified against negacyclic reference. |
| **N2** | **Dual-Scheme Reconfiguration** | Parameterized Montgomery multiplier and dual twiddle support for both Dilithium ($q=8380417$) and Kyber ($q=3329$). | One netlist serves both digital signatures (ML-DSA) and key exchange (ML-KEM). |
| **N3** | **RISC-V Custom-Instruction + Self-DMA** | PicoRV32 PCPI custom instruction (`custom0`) handshake paired with a Wishbone-lite bus-master DMA engine. | Eliminates the 256-word MMIO programmed-I/O bottleneck; transparent memory-to-memory transforms. |
| **N4** | **ROM-less On-The-Fly Twiddle Generator** | Computes Montgomery-domain twiddle factors on-the-fly using iterated modular multiplication and stage seeds. | Slashes twiddle memory area by over 80% compared to a 256-word lookup ROM. |
| **N5** | **Constant-Time Control & Masking** | Strictly data-independent FSM cycle schedule paired with a first-order Boolean/modular share splitter and combiner. | Eliminates timing side-channels and provides power-analysis / DPA resistance. |
| **N6** | **LLM & ML Microarchitecture DSE** | AI-guided PQC ring compiler, DPA side-channel reasoner, and active learning surrogate optimization. | Automatically compiles ring parameters, reasons on leakage risk, and discovers the Pareto front. |

---

## 3. System Architecture & Interconnect

```
                +---------------------------------------+
                |              OpenNTT SoC              |
                |                                       |
  +---------+   |  +------------+       +------------+  |
  | PicoRV32|---|->| ntt_pcpi   |------>|  ntt_top   |  |
  | RISC-V  |<--|--| (custom0)  |       | (Datapath) |  |
  +---------+   |  +------------+       +-----+------+  |
       |        |                             |         |
       v        |  +------------+             v         |
 [Wishbone Bus]-|->|  ntt_dma   |<----->[ Coeff RAM ]  |
       ^        |  | (Bus Master|       [ (2N x 24b) ]  |
       |        |  +------------+                       |
       v        +---------------------------------------+
  +---------+
  | Shared  |
  |  SRAM   |
  +---------+
```

### Module Hierarchy
* [`src/ntt_top.v`](src/ntt_top.v) : Top-level accelerator engine & constant-time FSM controller.
* [`src/butterfly.v`](src/butterfly.v) : Dual-mode Cooley-Tukey (CT) and Gentleman-Sande (GS) butterfly arithmetic cell.
* [`src/butterfly_radix4.v`](src/butterfly_radix4.v) : High-throughput 4-point Radix-4 butterfly arithmetic unit.
* [`src/banked_mem_ctrl.v`](src/banked_mem_ctrl.v) : Conflict-free 4-bank interleaved SRAM memory controller.
* [`src/fault_detect.v`](src/fault_detect.v) : Real-time Fault-Injection Attack (FIA) residue invariant detector.
* [`src/perf_counters.v`](src/perf_counters.v) : Hardware performance profiling & Hamming-distance side-channel toggle counters.
* [`src/mod_mul.v`](src/mod_mul.v) : 1-cycle Montgomery modular multiplier ($R=2^{32}$).
* [`src/coeff_ram.v`](src/coeff_ram.v) : Dual-port coefficient memory with 512-word ($2N$) capacity for regions A and B.
* [`src/twiddle_rom.v`](src/twiddle_rom.v) : Bit-reversed pre-scaled Montgomery twiddle table.
* [`src/twiddle_gen.v`](src/twiddle_gen.v) : Iterated Montgomery on-the-fly twiddle factor generator (N4).
* [`src/mask.v`](src/mask.v) : First-order share splitting and recombination unit for side-channel defense (N5).
* [`src/soc/ntt_pcpi.v`](src/soc/ntt_pcpi.v) : PicoRV32 PCPI custom-instruction decoder (N3).
* [`src/soc/ntt_dma.v`](src/soc/ntt_dma.v) : Wishbone bus master DMA controller (N3).
* [`src/soc/open_ntt_soc.v`](src/soc/open_ntt_soc.v) : SoC wrapper integrating CPU bus, DMA arbiter, and OpenNTT.

---

## 4. Repository Structure

```
open_ntt_pqc_accelerator/
├── README.md               # Project documentation
├── open_ntt.ipynb          # Interactive Master Jupyter Notebook
├── docs/
│   ├── architecture.md     # Microarchitecture specification
│   └── system_architecture.md # Full system blueprint & novelty mapping
├── dse/
│   ├── dse_agent.py        # ML-driven surrogate optimizer (N6)
│   ├── ml_model.py         # Surrogate training, evaluation & parity plots
│   └── llm_pqc_optimizer.py # LLM PQC ring compiler & DPA side-channel reasoner
├── figures/
│   ├── ml_surrogate_parity.png # High-resolution evaluation parity charts
│   └── waveform_timing.png     # Digital logic timing waveform diagram
├── src/
│   ├── butterfly.v         # Radix-2 Butterfly datapath
│   ├── butterfly_radix4.v  # Radix-4 High-Throughput Butterfly unit
│   ├── banked_mem_ctrl.v   # Conflict-free 4-bank memory controller
│   ├── fault_detect.v      # Fault Injection Attack detector
│   ├── perf_counters.v     # Performance & Hamming toggle counters
│   ├── coeff_ram.v         # Coefficient RAM
│   ├── mask.v              # Side-channel masking unit
│   ├── mod_mul.v           # Montgomery modular multiplier
│   ├── ntt_golden.py       # Python golden reference model
│   ├── ntt_top.v           # Unified accelerator top-level
│   ├── twiddle_dilithium.* # Dilithium twiddle tables (.vh, .hex)
│   ├── twiddle_kyber.*     # Kyber twiddle tables (.vh, .hex)
│   ├── twiddle_gen.v       # On-the-fly twiddle generator
│   ├── twiddle_rom.v       # Twiddle ROM
│   └── soc/
│       ├── ntt_dma.v       # Bus master DMA engine
│       ├── ntt_pcpi.v      # RISC-V PCPI custom-instruction decoder
│       └── open_ntt_soc.v  # Full SoC top-level wrapper
└── tb/
    ├── run_tests.py        # Test suite runner (all 10 modules)
    ├── test_butterfly.py   # Butterfly testbench
    ├── test_butterfly_radix4.py # Radix-4 butterfly testbench
    ├── test_banked_mem.py  # 4-bank memory testbench
    ├── test_fault_detect.py # Fault injection testbench
    ├── test_perf_counters.py # Performance counter testbench
    ├── test_mask.py        # Masking unit testbench
    ├── test_mod_mul.py     # Montgomery multiplier testbench
    ├── test_ntt.py         # Full poly-mult testbench
    ├── test_soc.py         # SoC & custom instruction testbench
    └── test_twiddle_gen.py # On-the-fly generator testbench
```

---

## 5. Verification & Testing

The verification framework uses **cocotb** and **Icarus Verilog**, co-simulated with the Python golden model ([`src/ntt_golden.py`](src/ntt_golden.py)).

### Running All 10 Automated Tests
```bash
python tb/run_tests.py all
```

### Running Individual Test Suites
```bash
python tb/run_tests.py mod_mul          # 2000 randomized Montgomery multiplier trials
python tb/run_tests.py butterfly        # 3000 CT & GS butterfly operations
python tb/run_tests.py butterfly_radix4 # 4-point Radix-4 butterfly operations
python tb/run_tests.py banked_mem       # Parallel 4-way conflict-free memory access
python tb/run_tests.py fault_detect     # Fault injection & tamper containment
python tb/run_tests.py perf_counters    # Cycle & Hamming distance toggle counting
python tb/run_tests.py ntt              # Full polynomial multiply vs negacyclic reference
python tb/run_tests.py twiddle_gen      # On-the-fly generator stage & step verification
python tb/run_tests.py mask             # 100 randomized share split & combine trials
python tb/run_tests.py soc              # PicoRV32 custom0 PCPI handshake & transform
```

---

## 6. Design Space Exploration (DSE)

To run the machine-learning-assisted Pareto optimizer across microarchitecture parameters:
```bash
python dse/dse_agent.py
```

---

## 7. License

OpenNTT is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
