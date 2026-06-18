import os
import sys
import numpy as np
from datetime import datetime
from collections import namedtuple
import matplotlib.pyplot as plt

# 1. 경로 인식 방어벽 (VS Code 및 실행 환경 안정화)
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from simglucose.patient.t1dpatient import T1DPatient
from simglucose.sensor.cgm import CGMSensor
from simglucose.actuator.pump import InsulinPump
from simglucose.simulation.env import T1DSimEnv

# ====================================================================
# 2. 이중제어 규격 시나리오 (기본 식사 + dynamic 구호 당분)
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
# 3. 환자군 N=30 무작위 셔플 및 분할 (시드 고정)
# ====================================================================
all_patients = [f'adult#{str(i).zfill(3)}' for i in range(1, 11)] + \
               [f'adolescent#{str(i).zfill(3)}' for i in range(1, 11)] + \
               [f'child#{str(i).zfill(3)}' for i in range(1, 11)]

np.random.seed(42)  
shuffled_patients = np.random.permutation(all_patients).tolist()

dev_cohort = shuffled_patients[:20]  
val_cohort = shuffled_patients[20:]  

# ====================================================================
# 4. 완전미분 기반 이중제어 변수 아키텍처 컨트롤러 (Refactored)
# ====================================================================
class TigrogenDualVariableController:
    def __init__(self, patient_object, patient_name, target_meal_carbs=58.8):
        self.prev_trend = 0.0
        
        # 환자 고유 생체 파라미터 계수 수집 (CR: 탄수화물 비율, CF: 인슐린 민감도 지수)
        self.CR = getattr(patient_object, 'CR', None)
        self.CF = getattr(patient_object, 'CF', None)
        
        # 방어적 예외 처리: 데이터 누락 시 군집별 표준 임계값 매핑
        if self.CR is None or self.CF is None:
            if 'child' in patient_name:
                self.CR, self.CF = 20.0, 5.0
            elif 'adolescent' in patient_name:
                self.CR, self.CF = 13.0, 3.5
            else:
                self.CR, self.CF = 10.0, 2.5
                
        # [제어 가중치 파라미터 변수화 - 교수님 지적 방어존]
        self.target_bg = 115.0            # 목표 혈당 기선 (mg/dL)
        self.g_safe = 95.0                # 저혈당 방어 기선 (mg/dL)
        self.theta_critical = 0.15        # 가속도 급증 임계치
        
        # 선형 제어 튜닝 가중치 (Empirical Tuning Weights)
        self.w_bolus_meal = 1.30          # 식사 볼루스 과보상 계수
        self.w_bolus_accel = 3.5          # 가속도 기반 추가 볼루스 계수
        self.w_basal_error = 0.015        # 혈당 편차 비례 기저 계수
        self.w_basal_trend = 0.06         # 혈당 변화량 비례 기저 계수
        self.w_rescue_gain = 0.18         # 구호 당분 주입 게인
        
        # 입력받은 식사량을 기준으로 이상적 식사 볼루스 계산 (하드코딩 제거)
        self.ideal_meal_bolus = (target_meal_carbs / self.CR)
        
    def get_control_actions(self, current_time, cgm_val, prev_cgm, meal_time):
        error = cgm_val - self.target_bg
        
        # 1차 미분(Trend) 및 2차 미분(Acceleration) 계산
        trend = cgm_val - prev_cgm
        acceleration = trend - self.prev_trend
        self.prev_trend = trend
        
        basal_dose = 0.0
        bolus_dose = 0.0
        rescue_glucose = 0.0  
        
        # [제어 루프 1: 인슐린 주입 회로]
        # 식사 정각 동기화 볼루스 투여
        if current_time == meal_time:
            bolus_dose = self.ideal_meal_bolus * self.w_bolus_meal + max(0, error / self.CF)
            return basal_dose, bolus_dose, rescue_glucose

        # 혈당 상승 가속도 급증 시 선제적 볼루스 투여 (Preemptive Bolus)
        if acceleration > self.theta_critical and cgm_val > self.target_bg:
            bolus_dose = (acceleration * self.w_bolus_accel) / self.CF

        # 기저 인슐린(Basal) 실시간 미분 비례 투여
        if cgm_val > self.target_bg:
            basal_dose = (error * self.w_basal_error + max(0, trend) * self.w_basal_trend) / self.CF
        elif self.g_safe <= cgm_val <= self.target_bg:
            basal_dose = 0.05 / self.CF
        else:
            basal_dose = 0.0

        # [제어 루프 2: 구호 당분 투여 회로 (Dual-Variable Predictive Loop)]
        # 25분 뒤의 혈당 평형 상태를 선제 예측 (Taylor Series 근사 방식 원리 적용)
        predicted_bg_25min = cgm_val + (trend * 5) + (acceleration * 2.5)
        
        if predicted_bg_25min < self.g_safe or cgm_val < 100:
            basal_dose = 0.0
            bolus_dose = 0.0
            
            needed_bg_recovery = self.g_safe - predicted_bg_25min
            if trend < 0 or cgm_val < 100:
                rescue_glucose = (needed_bg_recovery / self.CF) * self.CR * self.w_rescue_gain
                rescue_glucose = np.clip(rescue_glucose, 2.0, 15.0)  # 하드웨어 주입 제한 마진

        return basal_dose, bolus_dose, rescue_glucose

# ====================================================================
# 5. 시뮬레이션 구동 및 통계 매트릭스 수집 엔진
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
    print(f"🎯 [{title} INTEGRITY REPORT]")
    print("="*70)
    print(f" 1. 총 검증 인구 수 (Cohort Population)       : N = {len(cohort_list)} 명")
    print(f" 2. 식후 최고 피크 평균 혈당 (Mean Peak BG)    : {np.mean(peak_states):.2f} mg/dL")
    print(f" 3. 시뮬레이션 종단 평균 혈당 (Final Mean BG)   : {np.mean(final_states):.2f} mg/dL")
    print(f" 4. 전 가상환자 중 최저 혈당 기록 (Absolute Min): {np.min(min_states):.2f} mg/dL")
    print("="*70 + "\n")
    
    return results

# 시뮬레이션 가동 (정규 식사 규격 적용)
TARGET_CARBS = 58.8
dev_results = run_cohort_simulation(dev_cohort, "Development Cohort (N=20)", base_carbs=TARGET_CARBS)
val_results = run_cohort_simulation(val_cohort, "Validation Cohort (N=10)", base_carbs=TARGET_CARBS)

# ====================================================================
# 6. 최종 결과 시각화
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
print(f"🎨 [시각화 무결성] 고해상도 그래프 파일이 저장되었습니다:\n -> {output_path}\n")

plt.show()