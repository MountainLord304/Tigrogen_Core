# 🚀 Tigrogen OS: Dual-Variable Control Engine (Core)

**Tigrogen OS**는 1형 당뇨병(T1D) 환자의 인지적 해방과 완벽한 혈당 제어를 위해 설계된 소프트웨어 중심의 차세대 생체 신호 제어 루프 엔진입니다. 본 저장소의 코어 아키텍처는 하드웨어의 물리적 한계를 극복하고, 입력 데이터의 고차 미분 분석을 통해 환자에게 선제적 행동 가이드를 제공합니다.

---

## 🎯 기술적 무결성 및 검증 규격 (Integrity Specifications)

* **FDA 승인 표준 시뮬레이터 연동**: 의료 학계 및 산업계 표준인 **UVA/Padova T1D Simulator (`simglucose`)** 파이썬 환경에서 엄격한 폐쇄 루프(Closed-Loop) 검증을 통과하였습니다.
* **철저한 데이터 분할 체계 (Data Segregation)**: 가상 환자군 $N=30$명을 무작위 셔플링하여 개발 데이터셋(**Development Cohort**, $N=20$)과 독립 검증 데이터셋(**Validation Cohort**, $N=10$)으로 명확히 분리, 과적합(Overfitting) 및 데이터 오염을 원천 차단했습니다.

---

## 🧬 핵심 알고리즘 아키텍처 (Algorithm Core)

### 1. 2차 미분(가속도) 기반 선제적 볼루스 회로 (Preemptive Bolus)
혈당이 이미 상승한 후 반응하는 사후 처방식 기존 알고리즘과 달리, 연속혈당측정기(CGM) 데이터의 1차 미분(Trend) 및 2차 미분(Acceleration, $\alpha$)을 실시간 연산합니다. 급격한 상승 가속도가 임계치($\theta_{\text{critical}}$)를 초과할 경우, 혈당 피크가 형성되기 전 인슐린 민감도 지수($CF$)를 반영한 **선제적 볼루스($\text{Bolus}_{\text{preemptive}}$)**를 계산하여 투여 회로를 가동합니다.

### 2. 테일러 급수 근사법 기반 25분 미래 예측 이중 제어 (Predictive Loop)
인체의 혈당 평형 상태를 수학적으로 모델링하기 위해 테일러 급수(Taylor Series) 2차 근사식을 적용합니다. 

$$\text{BG}_{\text{predicted}}(t+25) = \text{CGM}_{\text{val}} + 5\left(\frac{dG}{dt}\right) + 12.5\left(\frac{d^2G}{dt^2}\right)$$

이를 통해 25분 뒤의 저혈당 쇼크 및 급격한 혈당 이탈을 선제 예측하며, 시스템 임계 하한선($G_{\text{safe}}$) 미달 예측 시 인슐린 주입을 전면 차단하고 탄수화물 비율($CR$) 가중치를 계산하여 즉각적인 **구호 당분 섭취 가이드($\text{Actionable Guide}$)**를 동적으로 출력합니다.

---

## 📊 성능 평가 레포트 (Validation Results)

* **Target Blood Glucose Baseline**: $115 \text{ mg/dL}$
* **Hypoglycemia Defense Line ($G_{\text{safe}}$)**: $95 \text{ mg/dL}$
* 본 코어 엔진 구동 시 식후 피크 혈당의 안정적 억제 및 종단 평균 혈당의 타깃 기선 수렴을 안정적으로 증명하였으며, 전 가상 환자군에서 절대적 저혈당 위험 구역 진입이 완벽하게 방어됨을 확인하였습니다.

---

## 📜 저작권 및 연구 고지 (IP & Research Notice)

* **소유권**: 본 저장소의 모든 알고리즘 소스 코드 및 수학적 제어 루프 아키텍처의 지식재산권(IP)은 프로젝트 설계자인 **차주현 (Lead Architect)**에게 종속되어 있습니다.
* 본 저장소는 비공개(Private) 혹은 승인된 파트너십 하에 관리되며, 학술적/상업적 목적의 무단 복제, 유출 및 도용을 금지합니다.
