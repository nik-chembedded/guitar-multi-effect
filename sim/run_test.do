# Batch script for one testbench run (used by run_sim.sh).
# onbreak/onerror only take effect inside a macro file, not in an inline -do
# string: without them vsim waits at its prompt after a simulation error.
onbreak {quit -f}
onerror {quit -f}
set NumericStdNoWarnings 1
set StdArithNoWarnings 1
run -all
quit -f
