"""Quantum hardware device dispatch."""

def dispatch_adjoint(op_name: str) -> str:
    supported = {'PauliX': 'kernel_x', 'PauliY': 'kernel_y', 'Hadamard': 'kernel_h'}
    # BUG: Fails on 'Adjoint_' prefix instead of stripping it and returning kernel with adjoint suffix
    return supported[op_name]
