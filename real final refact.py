import os
import sys
import numpy as np
from datetime import datetime
from collections import namedtuple
import matplotlib.pyplot as plt

# 1. Environment Path Protection (VS Code & Execution Environment Stabilization)
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from simglucose.patient.t1dpatient import T1DPatient
from simglucose.sensor.cgm import CGMSensor
from simglucose.actuator.pump import InsulinPump
from simglucose.simulation.env import T1DSimEnv

# ====================================================================
# 2. Dual-Variable Scenario Specification (Standard Meal + Dynamic Rescue Carbs)
# ====================================================================
class TigrogenDualScenario:
    def __init__(self, base_carbs=58.8):
        self.start_time = datetime(2026, 6, 1, 8, 0, 0)
        self.initial_meal_given = False
        self.meal_time_minutes = 10  
        self.base_carbs = base_carbs       
        self.dynamic_rescue_carbs = 0.0
    
    def get_action(self, t):
        Action = namedtuple('Action', ['meal'])
        elapsed_minutes = (t - self.start_time).total_seconds() / 60.0
        
        total_meal = 0.0
        if elapsed_minutes >= self.meal_time_minutes and not self.initial_meal_given:
            self.initial_meal_given = True
            total_meal += self.base_carbs
            
        if self.dynamic_rescue_carbs > 0:
            total_meal += self.dynamic_rescue_carbs
            self.dynamic_rescue_carbs = 0.0  
            
        return Action(meal=total_meal)
    
    def reset(self, *args, **kwargs):
        self.initial_meal_given = False
        self.dynamic_rescue_carbs = 0.0

def get_cgm_value(obs):
    if hasattr(obs, 'CGM'): return obs.CGM
    if hasattr(obs, 'observation') and hasattr(obs.observation, 'CGM'): return obs.observation.CGM
    if isinstance(obs, tuple) and hasattr(obs[0], 'CGM'): return obs[0].CGM
    if isinstance(obs, list) and len(obs) > 0: return obs[0]
    return 120.0 

# ====================================================================
# 3. Patient Cohort N=30 Random Shuffling & Segregation (Fixed Seed)
# ====================================================================
all_patients = [f'adult#{str(i).zfill(3)}' for i in range(1, 11)] + \
               [f'adolescent#{str(i).zfill(3)}' for i in range(1, 11)] + \
               [f'child#{str(i).zfill(3)}' for i in range(1, 11)]

np.random.seed(42)  
shuffled_patients = np.random.permutation(all_patients).tolist()

dev_cohort = shuffled_patients[:20]  
val_cohort = shuffled_patients[20:]  

# ====================================================================
# 4. Derivative-Based Dual-Variable Controller Architecture
# ====================================================================
class TigrogenDualVariableController:
    def __init__(self, patient_object, patient_name, target_meal_carbs=58.8):
        self.prev_trend = 0.0
        
        # Collect patient-specific physiological parameters (CR: Carb Ratio, CF: Correction Factor)
        self.CR = getattr(patient_object, 'CR', None)
        self.CF = getattr(patient_object, 'CF', None)
        
        # Defensive fallback: Default cohort mappings if parameters are missing
        if self.CR is None or self.CF is None:
            if 'child' in patient_name:
                self.CR, self.CF = 20.0, 5.0
            elif 'adolescent' in patient_name:
                self.CR, self.CF = 13.0, 3.5
            else:
                self.CR, self.CF = 10.0, 2.5
                
        # [Control Weight Parameters]
        self.target_bg = 115.0            # Target Blood Glucose Baseline (mg/dL)
        self.g_safe = 95.0                # Hypoglycemia Safety Line (mg/dL)
        self.theta_critical = 0.15        # Acceleration Critical Spike Threshold
        
        # Empirical Control Tuning Weights
        self.w_bolus_meal = 1.30          # Meal Bolus Compensation Factor
        self.w_bolus_accel = 3.5          # Acceleration-based Additional Bolus Gain
        self.w_basal_error = 0.015        # Error-proportional Basal Gain
        self.w_basal_trend = 0.06         # Trend-proportional Basal Gain
        self.w_rescue_gain = 0.18         # Rescue Carbohydrate Injection Gain
        
        # Calculate ideal meal bolus dynamically based on input carbohydrates
        self.ideal_meal_bolus = (target_meal_carbs / self.CR)
        
    def get_control_actions(self, current_time, cgm_val, prev_cgm, meal_time):
        error = cgm_val - self.target_bg
        
        # Calculate 1st Derivative (Trend) and 2nd Derivative (Acceleration)
        trend = cgm_val - prev_cgm
        acceleration = trend - self.prev_trend
        self.prev_trend = trend
        
        basal_dose = 0.0
        bolus_dose = 0.0
        rescue_glucose = 0.0  
        
        # [Control Loop 1: Insulin Injection Circuit]
        # Synchronized Meal Bolus Delivery
        if current_time == meal_time:
            bolus_dose = self.ideal_meal_bolus * self.w_bolus_meal + max(0, error / self.CF)
            return basal_dose, bolus_dose, rescue_glucose

        # Preemptive Bolus on Glucose Acceleration Spikes
        if acceleration > self.theta_critical and cgm_val > self.target_bg:
            bolus_dose = (acceleration * self.w_bolus_accel) / self.CF

        # Real-time Derivative Proportional Basal Delivery
        if cgm_val > self.target_bg:
            basal_dose = (error * self.w_basal_error + max(0, trend) * self.w_basal_trend) / self.CF
        elif self.g_safe <= cgm_val <= self.target_bg:
            basal_dose = 0.05 / self.CF
        else:
            basal_dose = 0.0

        # [Control Loop 2: Rescue Carbohydrate Circuit (Dual-Variable Predictive Loop)]
        # 25-Min Future Metabolic Equilibrium Prediction (2nd-Order Taylor Series Expansion)
        predicted_bg_25min = cgm_val + (trend * 5) + (acceleration * 2.5)
        
        if predicted_bg_25min < self.g_safe or cgm_val < 100:
            basal_dose = 0.0
            bolus_dose = 0.0
            
            needed_bg_recovery = self.g_safe - predicted_bg_25min
            if trend < 0 or cgm_val < 100:
                rescue_glucose = (needed_bg_recovery / self.CF) * self.CR * self.w_rescue_gain
                rescue_glucose = np.clip(rescue_glucose, 2.0, 15.0)  # Hardware Delivery Safety Margin

        return basal_dose, bolus_dose, rescue_glucose

# ====================================================================
# 5. Simulation Driver & Statistical Matrix Collection Engine
# ====================================================================
def run_cohort_simulation(cohort_list, title, base_carbs=58.8):
    SIM_STEPS = 72  
    results = {}
    bg_matrix = np.zeros((len(cohort_list), SIM_STEPS + 1))
    
    print(f">> Running Simulation for {title}...")
    for idx, p_name in enumerate(cohort_list):
        patient = T1DPatient.withName(p_name)
        scenario = TigrogenDualScenario(base_carbs=base_carbs)
        env = T1DSimEnv(patient, CGMSensor.withName('Dexcom'), InsulinPump.withName('Insulet'), scenario)
        
        tg_os = TigrogenDualVariableController(patient, p_name, target_meal_carbs=base_carbs)
        
        obs = env.reset()
        current_bg = get_cgm_value(obs)
        
        bg_history = [current_bg]
        time_history = [0]
        bg_matrix[idx, 0] = current_bg
        prev_cgm = current_bg  
        
        for i in range(1, SIM_STEPS + 1):
            current_time = i * 5
            
            basal, bolus, rescue_carbs = tg_os.get_control_actions(
                current_time, current_bg, prev_cgm, env.scenario.meal_time_minutes
            )
            
            if rescue_carbs > 0:
                env.scenario.dynamic_rescue_carbs = rescue_carbs
            
            action = namedtuple('Action', ['basal', 'bolus'])(basal=basal, bolus=bolus)
            step_result = env.step(action)
            obs = step_result[0] if isinstance(step_result, tuple) else step_result
            
            prev_cgm = current_bg
            current_bg = get_cgm_value(obs)
            
            bg_history.append(current_bg)
            time_history.append(current_time)
            bg_matrix[idx, i] = current_bg
            
        results[p_name] = {'time': time_history, 'bg': bg_history}
        
    final_states = bg_matrix[:, -1]          
    peak_states = np.max(bg_matrix, axis=1)  
    min_states = np.min(bg_matrix, axis=1)   
    
    print("\n" + "="*70)
    print(f"🎯 [{title.upper()} INTEGRITY REPORT]")
    print("="*70)
    print(f" 1. Total Cohort Population                  : N = {len(cohort_list)}")
    print(f" 2. Postprandial Peak Mean BG                : {np.mean(peak_states):.2f} mg/dL")
    print(f" 3. Simulation Endpoint Mean BG              : {np.mean(final_states):.2f} mg/dL")
    print(f" 4. Absolute Minimum BG Recorded Across All  : {np.min(min_states):.2f} mg/dL")
    print("="*70 + "\n")
    
    return results

# Run Simulations (Standard Meal Scenario)
TARGET_CARBS = 58.8
dev_results = run_cohort_simulation(dev_cohort, "Development Cohort (N=20)", base_carbs=TARGET_CARBS)
val_results = run_cohort_simulation(val_cohort, "Validation Cohort (N=10)", base_carbs=TARGET_CARBS)

# ====================================================================
# 6. Final Performance Visualization
# ====================================================================
fig, axes = plt.subplots(1, 2, figsize=(18, 6.5), sharey=True)

# Plot 1: Development Cohort
axes[0].set_title('Phase 1: Tigrogen OS Dual-Variable Control (N=20)', fontsize=14, fontweight='bold', pad=15)
for p_name, data in dev_results.items():
    axes[0].plot(data['time'], data['bg'], color='#3498db', alpha=0.35, linewidth=1.5)
axes[0].axhline(y=70, color='#e74c3c', linestyle='--', alpha=0.8, linewidth=2, label='Hypoglycemia (70)')
axes[0].axhline(y=180, color='#f39c12', linestyle='--', alpha=0.8, linewidth=2, label='Hyperglycemia (180)')
axes[0].axhline(y=115, color='purple', linestyle=':', alpha=0.8, linewidth=1.5, label='Tigrogen Target (115)')
axes[0].set_xlabel('Time (minutes)', fontsize=12, labelpad=10)
axes[0].set_ylabel('Blood Glucose (mg/dL)', fontsize=12, labelpad=10)
axes[0].set_ylim(50, 220)
axes[0].grid(True, linestyle=':', alpha=0.6)
axes[0].legend(loc='upper right', fontsize=10)

# Plot 2: Validation Cohort
axes[1].set_title('Phase 2: Tigrogen OS Dual-Variable Validation (N=10)', fontsize=14, fontweight='bold', pad=15)
for p_name, data in val_results.items():
    axes[1].plot(data['time'], data['bg'], color='#2ecc71', alpha=0.45, linewidth=1.8)
axes[1].axhline(y=70, color='#e74c3c', linestyle='--', alpha=0.8, linewidth=2)
axes[1].axhline(y=180, color='#f39c12', linestyle='--', alpha=0.8, linewidth=2)
axes[1].axhline(y=115, color='purple', linestyle=':', alpha=0.8, linewidth=1.5)
axes[1].set_xlabel('Time (minutes)', fontsize=12, labelpad=10)
axes[1].set_ylim(50, 220)
axes[1].grid(True, linestyle=':', alpha=0.6)

plt.subplots_adjust(left=0.08, right=0.95, bottom=0.15, top=0.88, wspace=0.15)

output_path = os.path.join(current_dir, "Tigrogen_OS_Dual_Variable_Final_Proof.png")
plt.savefig(output_path, dpi=300, bbox_inches='tight')
print(f"🎨 [Visualization Complete] High-resolution graph saved at:\n -> {output_path}\n")

plt.show()
