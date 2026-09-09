"""
Golden reference model for the OpenNTT post-quantum-crypto accelerator.

Implements the Number Theoretic Transform (NTT) used by the NIST lattice
standards ML-DSA (Dilithium) and ML-KEM (Kyber), plus a schoolbook negacyclic
polynomial multiplier used as ground truth.

Two modes:
  * Dilithium: q = 8380417, n = 256, COMPLETE length-256 NTT (512 | q-1).
  * Kyber:     q = 3329,    n = 256, INCOMPLETE NTT (only 256 | q-1), base
               case is degree-1 polynomials multiplied modulo (x^2 - zeta).

All arithmetic here is plain Python big-int modular arithmetic. This module is
the reference the RTL is checked against; it is intentionally simple, not fast.
"""

from typing import List

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
DIL_Q = 8380417   # Dilithium modulus
DIL_N = 256
DIL_ROOT = 1753   # primitive 512th root of unity (2n-th) mod DIL_Q

KY_Q = 3329       # Kyber modulus
KY_N = 256
KY_ROOT = 17      # primitive 256th root of unity mod KY_Q


# ---------------------------------------------------------------------------
# Basic modular arithmetic
# ---------------------------------------------------------------------------
def modexp(base: int, exp: int, q: int) -> int:
    """Modular exponentiation."""
    result = 1
    base %= q
    while exp > 0:
        if exp & 1:
            result = (result * base) % q
        exp >>= 1
        base = (base * base) % q
    return result


def modinv(a: int, q: int) -> int:
    """Modular inverse via Fermat (q prime)."""
    return modexp(a, q - 2, q)


def modinv_general(a: int, m: int) -> int:
    """Modular inverse for any modulus m (extended Euclid). Requires gcd(a,m)=1."""
    g, x = _egcd(a % m, m)
    if g != 1:
        raise ValueError("no inverse: gcd(%d,%d)=%d" % (a, m, g))
    return x % m


def _egcd(a: int, b: int):
    """Return (gcd, x) with a*x ≡ gcd (mod b)."""
    old_r, r = a, b
    old_s, s = 1, 0
    while r != 0:
        quot = old_r // r
        old_r, r = r, old_r - quot * r
        old_s, s = s, old_s - quot * s
    return old_r, old_s


def bit_reverse(i: int, bits: int) -> int:
    r = 0
    for _ in range(bits):
        r = (r << 1) | (i & 1)
        i >>= 1
    return r


# ---------------------------------------------------------------------------
# Montgomery reduction (this mirrors the hardware datapath exactly).
#
# R = 2^32. For a modulus q, define:
#     QPRIME = (-q^{-1}) mod R
# REDC(T) for 0 <= T < q*R returns  T * R^{-1} mod q :
#     m = ((T mod R) * QPRIME) mod R
#     t = (T + m*q) / R          (exact integer division)
#     if t >= q: t -= q
#
# montmul(a, b) = a * b * R^{-1} mod q. To make montmul(zeta, x) == zeta*x mod q,
# twiddles are stored pre-scaled into the Montgomery domain (multiplied by R).
# ---------------------------------------------------------------------------
MONT_R_BITS = 32
MONT_R = 1 << MONT_R_BITS


def mont_qprime(q: int) -> int:
    """QPRIME = (-q^{-1}) mod 2^32  (2^32 is not prime, use general inverse)."""
    return (-modinv_general(q, MONT_R)) % MONT_R


def redc(t: int, q: int) -> int:
    qprime = mont_qprime(q)
    m = ((t & (MONT_R - 1)) * qprime) & (MONT_R - 1)
    u = (t + m * q) >> MONT_R_BITS
    if u >= q:
        u -= q
    return u


def to_mont(a: int, q: int) -> int:
    """Map a into Montgomery domain: a * R mod q  (= REDC(a * R^2))."""
    r2 = (MONT_R * MONT_R) % q
    return redc(a * r2, q)


def from_mont(a: int, q: int) -> int:
    """Map a out of Montgomery domain: a * R^{-1} mod q."""
    return redc(a, q)


def montmul(a: int, b: int, q: int) -> int:
    """a * b * R^{-1} mod q."""
    return redc(a * b, q)


# ---------------------------------------------------------------------------
# Schoolbook negacyclic reference: multiply in Z_q[x] / (x^n + 1)
# ---------------------------------------------------------------------------
def poly_mul_negacyclic(a: List[int], b: List[int], q: int) -> List[int]:
    n = len(a)
    tmp = [0] * (2 * n)
    for i in range(n):
        ai = a[i]
        if ai == 0:
            continue
        for j in range(n):
            tmp[i + j] = (tmp[i + j] + ai * b[j]) % q
    out = [0] * n
    for i in range(n):
        # x^n = -1  ->  fold high half back with a sign flip
        out[i] = (tmp[i] - tmp[i + n]) % q
    return out


# ---------------------------------------------------------------------------
# Complete NTT (Dilithium style): in-place Cooley-Tukey, output in
# bit-reversed order. Twiddles are powers of the 2n-th root in bit-reversed
# order (the standard "merged" negacyclic NTT, no separate pre-weighting).
# ---------------------------------------------------------------------------
def _zetas_complete(root: int, n: int, q: int) -> List[int]:
    bits = n.bit_length() - 1  # log2(n)
    return [modexp(root, bit_reverse(i, bits), q) for i in range(n)]


def ntt_complete(a: List[int], q: int, root: int) -> List[int]:
    a = list(a)
    n = len(a)
    zetas = _zetas_complete(root, n, q)
    k = 0
    length = n // 2
    while length >= 1:
        start = 0
        while start < n:
            k += 1
            zeta = zetas[k]
            for j in range(start, start + length):
                t = (zeta * a[j + length]) % q
                a[j + length] = (a[j] - t) % q
                a[j] = (a[j] + t) % q
            start += 2 * length
        length >>= 1
    return a


def intt_complete(a: List[int], q: int, root: int) -> List[int]:
    a = list(a)
    n = len(a)
    zetas = _zetas_complete(root, n, q)
    k = n
    length = 1
    while length < n:
        start = 0
        while start < n:
            k -= 1
            zeta = (-zetas[k]) % q  # inverse butterfly uses -zeta
            for j in range(start, start + length):
                t = a[j]
                a[j] = (t + a[j + length]) % q
                a[j + length] = (t - a[j + length]) % q
                a[j + length] = (zeta * a[j + length]) % q
            start += 2 * length
        length <<= 1
    ninv = modinv(n, q)
    return [(x * ninv) % q for x in a]


def poly_mul_ntt_complete(a: List[int], b: List[int], q: int, root: int) -> List[int]:
    fa = ntt_complete(a, q, root)
    fb = ntt_complete(b, q, root)
    fc = [(x * y) % q for x, y in zip(fa, fb)]
    return intt_complete(fc, q, root)


# ---------------------------------------------------------------------------
# Montgomery-domain complete NTT. Twiddles are stored in Montgomery domain so
# each butterfly uses one montmul(). This is the exact operation sequence the
# RTL performs, so its output is the parity target for the hardware.
# ---------------------------------------------------------------------------
def _zetas_complete_mont(root: int, n: int, q: int) -> List[int]:
    return [to_mont(z, q) for z in _zetas_complete(root, n, q)]


def modadd(a: int, b: int, q: int) -> int:
    """Reference for hardware mod_add: (a + b) with one conditional subtract."""
    s = a + b
    return s - q if s >= q else s


def modsub(a: int, b: int, q: int) -> int:
    """Reference for hardware mod_sub: (a - b) with one conditional add."""
    d = a - b
    return d + q if d < 0 else d


def twiddle_table_mont(q: int, root: int, n: int) -> List[int]:
    """ROM contents: zeta[k] = to_mont(root^bitreverse(k)) for k in 0..n-1.

    The control FSM increments k from 1 upward, so index 0 is unused (kept as a
    placeholder so ROM address == k). This is the exact table twiddle_rom loads.
    """
    return _zetas_complete_mont(root, n, q)


def write_twiddle_hex(path: str, q: int, root: int, n: int, width_nibbles: int = 6) -> None:
    """Write the Montgomery-domain twiddle table as a $readmemh file (one hex
    word per line, `width_nibbles` hex digits = ceil(WIDTH/4))."""
    table = twiddle_table_mont(q, root, n)
    with open(path, "w") as f:
        for z in table:
            f.write(("%0" + str(width_nibbles) + "x\n") % z)


def ntt_complete_mont(a: List[int], q: int, root: int) -> List[int]:
    a = list(a)
    n = len(a)
    zetas = _zetas_complete_mont(root, n, q)
    k = 0
    length = n // 2
    while length >= 1:
        start = 0
        while start < n:
            k += 1
            zeta = zetas[k]
            for j in range(start, start + length):
                t = montmul(zeta, a[j + length], q)  # zeta*a[j+len] mod q
                a[j + length] = (a[j] - t) % q
                a[j] = (a[j] + t) % q
            start += 2 * length
        length >>= 1
    return a


# ---------------------------------------------------------------------------
# Montgomery-domain unified polynomial multiply. This is the exact operation
# sequence the unified hardware engine (N1) performs:
#
#   coefficients are converted into the Montgomery domain, the forward NTT
#   (Cooley-Tukey), the point-wise product (single Montgomery multiply), and the
#   inverse NTT (Gentleman-Sande + scale by n^{-1}) all stay in the Montgomery
#   domain, then the result is converted back out.
#
# ntt_complete_mont() above, when fed Montgomery-domain data, keeps the data in
# the Montgomery domain (zeta_mont * x_mont / R = (zeta*x)_mont), so it is reused
# as the forward transform here.
# ---------------------------------------------------------------------------
def intt_complete_mont(a: List[int], q: int, root: int) -> List[int]:
    """Inverse NTT (Gentleman-Sande) on Montgomery-domain data, incl. n^{-1}."""
    a = list(a)
    n = len(a)
    zetas = _zetas_complete_mont(root, n, q)  # Montgomery-domain twiddles
    ninv_mont = to_mont(modinv(n, q), q)
    k = n
    length = 1
    while length < n:
        start = 0
        while start < n:
            k -= 1
            zeta_gs = (q - zetas[k]) % q       # -zeta in Montgomery domain
            for j in range(start, start + length):
                t = a[j]
                a[j] = (t + a[j + length]) % q
                a[j + length] = (t - a[j + length]) % q
                a[j + length] = montmul(zeta_gs, a[j + length], q)
            start += 2 * length
        length <<= 1
    return [montmul(x, ninv_mont, q) for x in a]


def pointwise_mont(a: List[int], b: List[int], q: int) -> List[int]:
    """Point-wise product of two Montgomery-domain vectors (one montmul each)."""
    return [montmul(a[i], b[i], q) for i in range(len(a))]


def poly_mul_hw(a: List[int], b: List[int], q: int, root: int) -> List[int]:
    """Full polynomial multiply exactly as the unified engine computes it."""
    am = [to_mont(x, q) for x in a]
    bm = [to_mont(x, q) for x in b]
    fa = ntt_complete_mont(am, q, root)
    fb = ntt_complete_mont(bm, q, root)
    fc = pointwise_mont(fa, fb, q)
    cc = intt_complete_mont(fc, q, root)
    return [from_mont(x, q) for x in cc]


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import random
    random.seed(0)

    # Dilithium complete NTT round-trip + convolution check
    n, q, root = DIL_N, DIL_Q, DIL_ROOT
    a = [random.randrange(q) for _ in range(n)]
    b = [random.randrange(q) for _ in range(n)]

    rt = intt_complete(ntt_complete(a, q, root), q, root)
    assert rt == a, "Dilithium INTT(NTT(a)) round-trip FAILED"

    ref = poly_mul_negacyclic(a, b, q)
    got = poly_mul_ntt_complete(a, b, q, root)
    assert ref == got, "Dilithium NTT convolution != schoolbook negacyclic"

    print("Dilithium complete NTT: round-trip OK, convolution OK  (n=%d q=%d)" % (n, q))

    # Montgomery datapath parity: plain NTT == Montgomery-domain NTT
    plain = ntt_complete(a, q, root)
    mont = ntt_complete_mont(a, q, root)
    assert plain == mont, "Montgomery-domain NTT != plain NTT"
    print("Montgomery datapath parity: OK  (QPRIME=%d, R=2^%d)" % (mont_qprime(q), MONT_R_BITS))

    # Unified poly-mult (mont-domain NTT + pointwise + INTT) == schoolbook
    hw = poly_mul_hw(a, b, q, root)
    ref2 = poly_mul_negacyclic(a, b, q)
    assert hw == ref2, "poly_mul_hw != schoolbook negacyclic"
    print("Unified poly-mult (mont NTT+PWM+INTT): OK, matches schoolbook")

    print("All golden-model self-tests PASSED.")
