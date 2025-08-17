
import numpy as np
import matplotlib.pyplot as plt
from scipy.sparse import diags
from scipy.sparse.linalg import spsolve
import pandas as pd
import os
from datetime import datetime
import time

class PCMSimulation:
    def __init__(self, length=0.1, n_nodes=101, T_solidus=4.0, T_liquidus=5.0,
                 T_initial=2.0, rho=1000, cp_solid=2000, cp_liquid=2500,
                 k_solid=0.5, k_liquid=0.3, L_fusion=334000):
        """
        Initialize PCM simulation parameters

        Parameters:
        - length: Domain length (m)
        - n_nodes: Number of nodes
        - T_solidus: Solidus temperature (°C)
        - T_liquidus: Liquidus temperature (°C)
        - T_initial: Initial temperature (°C)
        - rho: Density (kg/m³)
        - cp_solid: Specific heat of solid (J/kg·K)
        - cp_liquid: Specific heat of liquid (J/kg·K)
        - k_solid: Thermal conductivity of solid (W/m·K)
        - k_liquid: Thermal conductivity of liquid (W/m·K)
        - L_fusion: Latent heat of fusion (J/kg)
        """
        self.length = length
        self.n_nodes = n_nodes
        self.dx = length / (n_nodes - 1)
        self.x = np.linspace(0, length, n_nodes)

        # Material properties
        self.T_solidus = T_solidus
        self.T_liquidus = T_liquidus
        self.T_initial = T_initial
        self.rho = rho
        self.cp_solid = cp_solid
        self.cp_liquid = cp_liquid
        self.k_solid = k_solid
        self.k_liquid = k_liquid
        self.L_fusion = L_fusion

        # Initialize temperature field
        self.T = np.full(n_nodes, T_initial)

        # Time parameters
        self.dt = 0.1  # Time step (s)
        self.time = 0.0

        # Data storage
        self.time_history = []
        self.melt_fraction_history = []
        self.temperature_history = []

    def calculate_melt_fraction(self, temperature):
        """Calculate melt fraction based on temperature"""
        melt_fraction = np.zeros_like(temperature)

        # Solid phase
        melt_fraction[temperature <= self.T_solidus] = 0.0

        # Liquid phase
        melt_fraction[temperature >= self.T_liquidus] = 1.0

        # Mushy zone
        mushy_mask = (temperature > self.T_solidus) & (temperature < self.T_liquidus)
        melt_fraction[mushy_mask] = (temperature[mushy_mask] - self.T_solidus) / (self.T_liquidus - self.T_solidus)

        return melt_fraction

    def calculate_effective_properties(self, temperature):
        """Calculate effective thermal properties based on temperature"""
        melt_fraction = self.calculate_melt_fraction(temperature)

        # Effective specific heat (including latent heat effect)
        cp_eff = np.zeros_like(temperature)
        k_eff = np.zeros_like(temperature)

        for i in range(len(temperature)):
            if temperature[i] <= self.T_solidus:
                cp_eff[i] = self.cp_solid
                k_eff[i] = self.k_solid
            elif temperature[i] >= self.T_liquidus:
                cp_eff[i] = self.cp_liquid
                k_eff[i] = self.k_liquid
            else:
                # Mushy zone - linear interpolation
                cp_eff[i] = self.cp_solid + melt_fraction[i] * (self.cp_liquid - self.cp_solid)
                k_eff[i] = self.k_solid + melt_fraction[i] * (self.k_liquid - self.k_solid)

                # Add latent heat effect
                cp_eff[i] += self.L_fusion / (self.T_liquidus - self.T_solidus)

        return cp_eff, k_eff

    def solve_heat_equation(self, T_boundary, max_time=1000, save_interval=1.0):
        """
        Solve 1D heat equation with phase change

        Parameters:
        - T_boundary: Boundary temperature (°C)
        - max_time: Maximum simulation time (s)
        - save_interval: Data saving interval (s)
        """
        print(f"Starting simulation with boundary temperature: {T_boundary}°C")

        self.T = np.full(self.n_nodes, self.T_initial)  # Reset temperature
        self.time = 0.0
        self.time_history = []
        self.melt_fraction_history = []
        self.temperature_history = []

        save_counter = 0
        next_save_time = 0

        while self.time < max_time:
            # Calculate effective properties
            cp_eff, k_eff = self.calculate_effective_properties(self.T)

            # Calculate thermal diffusivity
            alpha = k_eff / (self.rho * cp_eff)

            # Ensure numerical stability
            max_alpha = np.max(alpha)
            if max_alpha > 0:
                dt_stable = 0.4 * self.dx**2 / max_alpha
                self.dt = min(self.dt, dt_stable)

            # Build coefficient matrix (implicit scheme)
            r = alpha * self.dt / self.dx**2

            # Create tridiagonal matrix
            main_diag = 1 + 2 * r
            off_diag = -r

            # Handle variable thermal diffusivity
            lower_diag = np.zeros(self.n_nodes - 1)
            upper_diag = np.zeros(self.n_nodes - 1)
            main_diag_array = np.zeros(self.n_nodes)

            for i in range(self.n_nodes):
                if i == 0:  # Left boundary
                    main_diag_array[i] = 1
                elif i == self.n_nodes - 1:  # Right boundary
                    main_diag_array[i] = 1
                else:
                    main_diag_array[i] = 1 + 2 * r[i]
                    if i > 0:
                        lower_diag[i-1] = -r[i]
                    if i < self.n_nodes - 1:
                        upper_diag[i] = -r[i]

            # Create sparse matrix
            A = diags([lower_diag, main_diag_array, upper_diag], [-1, 0, 1],
                     shape=(self.n_nodes, self.n_nodes), format='csr')

            # Right-hand side
            b = self.T.copy()

            # Apply boundary conditions
            b[0] = T_boundary
            b[-1] = T_boundary

            # Solve system
            T_new = spsolve(A, b)

            # Update temperature
            self.T = T_new
            self.time += self.dt

            # Save data at specified intervals
            if self.time >= next_save_time:
                melt_fraction = self.calculate_melt_fraction(self.T)
                avg_melt_fraction = np.mean(melt_fraction)

                self.time_history.append(self.time)
                self.melt_fraction_history.append(avg_melt_fraction)
                self.temperature_history.append(self.T.copy())

                next_save_time += save_interval

                # Print progress
                if save_counter % 50 == 0:
                    print(f"Time: {self.time:.1f}s, Avg Melt Fraction: {avg_melt_fraction:.3f}")

                save_counter += 1

                # Stop if 90% melted
                if avg_melt_fraction >= 0.9:
                    print(f"Simulation completed: 90% melt fraction reached at t={self.time:.1f}s")
                    break

        return np.array(self.time_history), np.array(self.melt_fraction_history)

    def plot_results(self, T_boundary):
        """Plot simulation results"""
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 12))

        # Plot 1: Melt fraction vs time
        ax1.plot(self.time_history, self.melt_fraction_history, 'b-', linewidth=2)
        ax1.set_xlabel('Time (s)')
        ax1.set_ylabel('Average Melt Fraction')
        ax1.set_title(f'Melt Fraction vs Time (T_boundary = {T_boundary}°C)')
        ax1.grid(True, alpha=0.3)

        # Plot 2: Temperature evolution at different positions
        times_to_plot = [0, len(self.time_history)//4, len(self.time_history)//2,
                        3*len(self.time_history)//4, len(self.time_history)-1]

        for i, time_idx in enumerate(times_to_plot):
            if time_idx < len(self.temperature_history):
                ax2.plot(self.x * 1000, self.temperature_history[time_idx],
                        label=f't = {self.time_history[time_idx]:.1f}s')

        ax2.axhline(y=self.T_solidus, color='r', linestyle='--', alpha=0.7, label='Solidus')
        ax2.axhline(y=self.T_liquidus, color='g', linestyle='--', alpha=0.7, label='Liquidus')
        ax2.set_xlabel('Position (mm)')
        ax2.set_ylabel('Temperature (°C)')
        ax2.set_title('Temperature Distribution Evolution')
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        # Plot 3: Final melt fraction distribution
        if len(self.temperature_history) > 0:
            final_melt_fraction = self.calculate_melt_fraction(self.temperature_history[-1])
            ax3.plot(self.x * 1000, final_melt_fraction, 'r-', linewidth=2)
            ax3.set_xlabel('Position (mm)')
            ax3.set_ylabel('Melt Fraction')
            ax3.set_title('Final Melt Fraction Distribution')
            ax3.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(f'pcm_results_T{T_boundary}.png', dpi=300, bbox_inches='tight')
        plt.show()


def generate_training_data(boundary_temperatures, output_dir='pcm_training_data'):
    """Generate training data for PINN"""

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Initialize simulation
    sim = PCMSimulation()

    # Store all data
    all_data = []

    print("Generating training data for PINN...")
    print(f"Boundary temperatures: {boundary_temperatures}")

    for T_boundary in boundary_temperatures:
        print(f"\n--- Processing T_boundary = {T_boundary}°C ---")
        a=time.time()
        # Run simulation
        time_array, melt_fraction_array = sim.solve_heat_equation(
            T_boundary=T_boundary,
            max_time=1000000,
            save_interval=4.0
        )
        print(f"Simulation completed in {time.time() - a:.2f} seconds")

        # Store data for this boundary condition
        for i, (t, mf) in enumerate(zip(time_array, melt_fraction_array)):
            all_data.append({
                'boundary_temperature': T_boundary,
                'time': t,
                'melt_fraction': mf,
                'solidus_temp': sim.T_solidus,
                'liquidus_temp': sim.T_liquidus,
                'initial_temp': sim.T_initial
            })

        # Plot results
        sim.plot_results(T_boundary)

        # Save individual dataset
        df_individual = pd.DataFrame({
            'time': time_array,
            'melt_fraction': melt_fraction_array,
            'boundary_temperature': T_boundary
        })
        df_individual.to_csv(f'{output_dir}/data_T{T_boundary}_4.csv', index=False)

    # Save combined dataset
    df_combined = pd.DataFrame(all_data)
    df_combined.to_csv(f'{output_dir}/combined_training_data_4.csv', index=False)

    print(f"\nTraining data generated successfully!")
    print(f"Total data points: {len(all_data)}")
    print(f"Data saved in: {output_dir}/")

    return df_combined


# Example usage
if __name__ == "__main__":
    # Define boundary temperatures for training
    boundary_temperatures = [20, 25, 30, 32, 35, 40, 45, 50]

    # Generate training data
    training_data = generate_training_data(boundary_temperatures)

    # Display summary statistics
    print("\n=== Training Data Summary ===")
    print(f"Shape: {training_data.shape}")
    print(f"Boundary temperatures: {training_data['boundary_temperature'].unique()}")
    print(f"Time range: {training_data['time'].min():.1f} - {training_data['time'].max():.1f} s")
    print(f"Melt fraction range: {training_data['melt_fraction'].min():.3f} - {training_data['melt_fraction'].max():.3f}")

    # Show sample data
    print("\n=== Sample Data ===")
    print(training_data.head(10))

    
