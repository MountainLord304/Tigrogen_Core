# 🚀 Tigrogen OS: Dual-Variable Control Engine (Core)

**Tigrogen OS** is a software-driven, next-generation bio-signal control loop engine designed for T1D (Type 1 Diabetes) patients to achieve cognitive freedom and optimal glucose management. This core repository addresses the physical limitations of current hardware and provides actionable, preemptive guides to patients via high-order derivative analysis of continuous glucose data.

---

## 🎯 Integrity Specifications & Validation Standard

* **FDA-Accepted Simulator Integration**: Validated under strict closed-loop simulation using the industry-standard UVA/Padova T1D Simulator (`simglucose`) Python environment.
* **Strict Data Segregation**: Utilized a randomized $N=30$ virtual patient cohort, strictly divided into a **Development Cohort ($N=20$)** and an independent **Validation Cohort ($N=10$)** to prevent overfitting and data leakage.

---

## 🧬 Algorithm Core Architecture

### 1. 2nd Derivative (Acceleration)-Based Preemptive Bolus Loop
Unlike reactive algorithms that respond only after blood glucose has already spiked, Tigrogen OS calculates real-time 1st derivative (Trend) and 2nd derivative (Acceleration, $\alpha$) from CGM data. When rapid acceleration exceeds critical thresholds ($\theta_{\text{critical}}$), it triggers a preemptive insulin sensitivity factor ($CF$)-adjusted bolus circuit **before** the glucose peak actually forms.

### 2. Taylor Series Approximation 25-Min Predictive Dual Loop
To mathematically model human metabolic equilibrium, a 2nd-order Taylor expansion is applied:

$$BG_{\text{predicted}}(t + 25) = CGM_{\text{val}} + 5\left(\frac{dG}{dt}\right) + 12.5\left(\frac{d^2G}{dt^2}\right)$$

This loop projects blood glucose 25 minutes ahead to preemptively detect severe drop risks or spikes. If predicted glucose falls below the system safety limit ($G_{\text{safe}}$), insulin delivery is halted immediately, and an **Actionable Rescue Carb Guide** is dynamically generated based on calculated carbohydrate ratios ($CR$).

---

## 📊 Performance Report (Validation Results)

* **Target Blood Glucose Baseline**: $115\text{ mg/dL}$
* **Hypoglycemia Defense Line ($G_{\text{safe}}$)**: $95\text{ mg/dL}$
* **Result**: Demonstrated stable suppression of postprandial glucose peaks and baseline convergence. The algorithm successfully prevented all virtual patients from entering critical hypoglycemia risk zones.

---

## 📜 IP & Research Notice

* **Ownership**: All algorithm source code and mathematical control architecture in this repository are the intellectual property of Lead Architect **Joohyeon Cha**.
* **License/Usage**: Managed under an open research PoC framework. For academic or collaborative inquiries, please contact the repository owner.
