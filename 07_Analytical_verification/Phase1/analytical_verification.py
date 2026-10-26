"""EEE4022S: independent fundamental spatial-decay check of PCB stack.
This is NOT an absolute field or torque prediction; geometry-based decay only.
Input FEM board coefficients from the archived final results package.
No third-party Python dependencies.
"""
import csv, math, pathlib
ROOT=pathlib.Path(__file__).parent
INPUT=ROOT/'Board_by_board_K_mNm_per_A.csv'
rows=list(csv.DictReader(INPUT.open(encoding='utf-8-sig',newline='')))
N_POLES=16; P=N_POLES//2; R_MEAN_MM=28.0
k=P/R_MEAN_MM   # mm^-1, fundamental pole spatial angular wavenumber
print('Geometry-only fundamental spatial-harmonic check')
print(f'pole pairs={P}; mean radius={R_MEAN_MM:g} mm; k=p/r={k:.6f} 1/mm')
print('Does not predict absolute B or K; local planar fundamental approximation.')
print('board,axial_distance_mm,FEM_Rev0_K_mNm_per_A,analytic_relative_to_board1,FEM_relative_to_board1,relative_difference_pp')
base=float(rows[0]['Rev0 S1 detailed']); z0=float(rows[0]['Distance from magnets (mm)'])
for r in rows[:5]:
 z=float(r['Distance from magnets (mm)']); fem=float(r['Rev0 S1 detailed'])
 a=math.exp(-k*(z-z0)); f=fem/base
 print(f"{r['Board']},{z:.3f},{fem:.4f},{a:.5f},{f:.5f},{100*(a-f):+.2f}")
ratio_ana=sum(math.exp(-k*(float(r['Distance from magnets (mm)'])-z0)) for r in rows[:5]); ratio_fem=sum(float(r['Rev0 S1 detailed']) for r in rows[:5])/base
print(f'Stack K / board-1 K: analytical {ratio_ana:.4f}, FEM {ratio_fem:.4f}')
print(f'Effective FEM decay fitted endpoints: {-math.log(float(rows[4]["Rev0 S1 detailed"])/base)/(float(rows[4]["Distance from magnets (mm)"])-z0):.5f} 1/mm')
print('Rev1-S S2 has a different magnetic boundary condition. Do not apply the Rev0 exponential blindly.')
