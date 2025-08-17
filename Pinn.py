
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

    

# def custom_split(X_norm, y_norm, validation_split, random_state=42):
#     '''
#     Wow a docstring
#     '''

#     print(X_norm.shape)
#     a,b,c,d=0,0,0,0
#     print(X_norm[0])

    
    
#     return a,b,c,d
    
    
    
# from tqdm import trange, tqdm

# import numpy as np
# import pandas as pd
# import tensorflow as tf
# from tensorflow import keras
# from keras import layers
# import matplotlib.pyplot as plt
# from sklearn.preprocessing import StandardScaler
# from sklearn.model_selection import train_test_split
# import os
# import time # Import time for progress indicator
# import pdb

# class PCM_PINN:
#     def __init__(self, hidden_layers=[32, 32], activation='tanh', # Reduced hidden layers
#                  learning_rate=0.001, T_solidus=4.0, T_liquidus=5.0):
#         """
#         Physics-Informed Neural Network for Phase Change Material

#         Parameters:
#         - hidden_layers: List of hidden layer sizes
#         - activation: Activation function
#         - learning_rate: Learning rate for optimizer
#         - T_solidus: Solidus temperature
#         - T_liquidus: Liquidus temperature
#         """
#         self.hidden_layers = hidden_layers
#         self.activation = activation
#         self.learning_rate = learning_rate
#         self.T_solidus = T_solidus
#         self.T_liquidus = T_liquidus

#         # Scalers for normalization
        
#         # self.scaler_input = StandardScaler()
#         # self.scaler_output = StandardScaler()

#         # Build neural network
#         self.build_network()

#         # Physics parameters (will be set during training)
#         self.alpha = None  # Thermal diffusivity
#         self.L_fusion = None # Latent heat
        


#     def build_network(self):
#         """Build the neural network architecture"""
#         # Input: [boundary_temperature, time]
#         inputs = keras.Input(shape=(2,), name='input')

#         # Hidden layers
#         x = inputs
#         for i, units in enumerate(self.hidden_layers):
#             x = layers.Dense(units, activation='tanh',
#                            name=f'hidden_{i+1}')(x)

#         # Output: melt_fraction
#         outputs = layers.Dense(1, activation='sigmoid', name='melt_fraction')(x)

#         # Create model
#         self.model = keras.Model(inputs=inputs, outputs=outputs, name='PCM_PINN')

#         # Compile model
#         self.model.compile(
#             optimizer=keras.optimizers.Adam(learning_rate=self.learning_rate),
#             loss='mse',
#             metrics=['mae']
#         )

#         print("Neural Network Architecture:")
#         self.model.summary()

#     def physics_loss(self, y_true, y_pred, inputs):
#         """
#         Calculate physics-informed loss based on heat equation
#         This is a simplified physics loss - in practice, you might want to include
#         more complex physics constraints
#         """
#         # Extract inputs
#         T_boundary = inputs[:, 0:1]
#         time = inputs[:, 1:2]

#         # Ensure inputs are float32 Tensors
#         T_boundary = tf.cast(T_boundary, tf.float32)
#         time = tf.cast(time, tf.float32)
#         inputs = tf.cast(inputs, tf.float32)


#         # Physics constraint: melt fraction should increase with temperature and time
#         # This is a simplified constraint - more complex physics can be added

#         # Temporal gradient (dmelt_fraction/dt should be >= 0)
#         with tf.GradientTape() as tape:
#             tape.watch(time)
#             # Ensure the model receives the inputs as a tensor for gradient calculation
#             melt_pred = self.model(inputs)

#         dmelt_dt = tape.gradient(melt_pred, time)

#         # Handle potential None gradient
#         if dmelt_dt is None:
#              physics_loss = tf.constant(0.0) # or a small penalty
#         else:
#             # Physics loss: penalize negative time derivatives
#             physics_loss = tf.reduce_mean(tf.square(tf.minimum(dmelt_dt, 0.0)))


#         return physics_loss

#     def custom_loss(self, y_true, y_pred, inputs, physics_weight=0.1):
#         """Combined data + physics loss"""
#         # Data loss
#         data_loss = tf.reduce_mean(tf.square(y_true - y_pred))

#         # Physics loss
#         phys_loss = self.physics_loss(y_true, y_pred, inputs)

#         # Combined loss
#         total_loss = data_loss + physics_weight * phys_loss

#         return total_loss

#     def prepare_data(self, data_path):
#         """Prepare training data from CSV file"""
#         print("Preparing data...") # Marker
#         # Load data
#         if isinstance(data_path, str):
#             df = pd.read_csv(data_path)
#         else:
#             df = data_path  # Assume it's already a DataFrame
        

#         print("Data")
#         print(len(df))
#         print(df.info())
#         # Prepare features and targets
#         X = df[['boundary_temperature', 'time']].values
#         y = df[['melt_fraction']].values

#         # # Normalize inputs and outputs
#         # print("I need the distribution of the data")
#         # print(type(X))
#         # df[df['boundary_temperature']==20]
#         # print('Value count')
#         # print(df['boundary_temperature'].value_counts())
#         # print("Histogram")
#         # df['boundary_temperature'].hist(bins=20)
#         # plt.xlabel('Boundary Temperature')
#         # plt.ylabel('Count')
#         # plt.title('Distribution of Boundary Temperature')
#         # plt.savefig("image.png")
#         # print("For the `mf")
#         # print(df['melt_fraction'].value_counts())

#         from sklearn.model_selection import GroupShuffleSplit

#         split = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
#         train_idx, test_idx = next(split.split(X, y, groups=df['boundary_temperature']))

#         # always 
#         X_train, X_val = X[train_idx], X[test_idx]
#         y_train, y_val = y[train_idx], y[test_idx]
#         print(len(X), len(y), len(df['boundary_temperature']))
#         mask = (df['boundary_temperature'] == 20).values
#         mask_45 = (df['boundary_temperature'] == 40).values
#         X_20 = X[mask]
#         X_45 = X[mask_45]
#         pdb.set_trace() 


#         # X_normalized = self.scaler_input.fit_transform(X)
#         # y_normalized = self.scaler_output.fit_transform(y)
#         print("Data preparation complete.") # Marker
#         return X_train, X_val, y_train, y_val



#     def train(self, data_path, epochs=1000, batch_size=32, validation_split=0.2,
#               physics_weight=0.1, verbose=1):
#         """Train the PINN model"""
#         print("Starting model training...") # Marker
#         print()
#         print("Make sure that the data is well distributed ")
#         X_train, X_val, y_train, y_val = self.prepare_data(data_path)
#         print("How does the data look now")
#         # Split data
#         print("Splitting data...") # Marker
#         # defining a custom split

#         # X_train, X_val, y_train, y_val = custom_split(X_norm, y_norm,validation_split,42)
   

#         print(f"Training data shape: {X_train.shape}")
#         print(f"Validation data shape: {X_val.shape}")

#         # Custom training loop for physics-informed loss
#         optimizer = keras.optimizers.Adam(learning_rate=self.learning_rate)

#         # Training history
#         train_losses = []
#         val_losses = []

#         print("Entering training loop...") # Marker
#         start_time = time.time() # For progress indicator
#         epochs =500
#         for epoch in trange(epochs):
#             print(f"--- Epoch {epoch+1}/{epochs} ---") # Epoch marker
#             epoch_loss = 0
#             n_batches = 0

#             # Batch training
#             for i in trange(0, len(X_train), batch_size):
#                 batch_X = X_train[i:i+batch_size]
#                 batch_y = y_train[i:i+batch_size]

#                 # print(f"  Processing batch {i//batch_size + 1}/{(len(X_train) + batch_size - 1) // batch_size}...") # Batch marker
#                 # print("    Calculating gradients...") # Gradient marker
#                 with tf.GradientTape() as tape:
#                     predictions = self.model(batch_X, training=True)
#                     loss = self.custom_loss(batch_y, predictions, batch_X, physics_weight)

#                 gradients = tape.gradient(loss, self.model.trainable_variables)
#                 # print("    Applying gradients...") # Apply gradients marker
#                 optimizer.apply_gradients(zip(gradients, self.model.trainable_variables))
#                 # print("    Gradients applied.") # Gradients applied marker

#                 epoch_loss += loss.numpy()
#                 n_batches += 1
#                 # print(f"    Batch {i//batch_size + 1} processed. Current epoch loss: {epoch_loss:.6f}") # Batch processed marker


#             # Validation loss
#             print("  Calculating validation loss...") # Validation marker
#             val_pred = self.model(X_val, training=False)
#             val_loss = tf.reduce_mean(tf.square(y_val - val_pred)).numpy()
#             print(f"  Validation loss: {val_loss:.6f}") # Validation loss marker

#             train_losses.append(epoch_loss / n_batches)
#             val_losses.append(val_loss)

#             # Print progress
#             if verbose and (epoch + 1) % 10 == 0: # Print more frequently for debugging
#                 elapsed_time = time.time() - start_time
#                 epochs_per_sec = (epoch + 1) / elapsed_time if elapsed_time > 0 else 0
#                 print(f"Epoch {epoch+1}/{epochs}, Train Loss: {train_losses[-1]:.6f}, "
#                       f"Val Loss: {val_losses[-1]:.6f} ({epochs_per_sec:.2f} epochs/sec)") # Progress indicator

#         print("Exiting training loop.") # Marker
#         # Store training history
#         self.history = {
#             'train_loss': train_losses,
#             'val_loss': val_losses
#         }

#         print("Training completed!") # Marker
#         return self.history







#     def predict(self, boundary_temperature, time_array):
#         """
#         Predict melt fraction for given boundary temperature and time array

#         Parameters:
#         - boundary_temperature: Boundary temperature (°C)
#         - time_array: Array of time points (s)

#         Returns:
#         - melt_fraction_array: Predicted melt fractions
#         """
#         # Prepare input
#         T_boundary_array = np.full_like(time_array, boundary_temperature)
#         X_input = np.column_stack([T_boundary_array, time_array])

#         # Normalize input
#         X_normalized = self.scaler_input.transform(X_input)

#         # Predict
#         y_pred_normalized = self.model.predict(tf.cast(X_normalized, tf.float32), verbose=0)

#         # Denormalize output
#         y_pred = self.scaler_output.inverse_transform(y_pred_normalized)

#         return y_pred.flatten()
    
    

#     def plot_training_history(self):
#         """Plot training history"""
#         print("Plotting training history...") # Marker
#         plt.figure(figsize=(10, 6))

#         plt.subplot(1, 2, 1)
#         plt.plot(self.history['train_loss'], label='Training Loss')
#         plt.plot(self.history['val_loss'], label='Validation Loss')
#         plt.xlabel('Epoch')
#         plt.ylabel('Loss')
#         plt.title('Training History')
#         plt.legend()
#         plt.grid(True, alpha=0.3)

#         plt.subplot(1, 2, 2)
#         plt.semilogy(self.history['train_loss'], label='Training Loss')
#         plt.semilogy(self.history['val_loss'], label='Validation Loss')
#         plt.xlabel('Epoch')
#         plt.ylabel('Loss (log scale)')
#         plt.title('Training History (Log Scale)')
#         plt.legend()
#         plt.grid(True, alpha=0.3)

#         plt.tight_layout()
#         plt.savefig('pinn_training_history.png', dpi=300, bbox_inches='tight')
#         plt.show()
#         print("Training history plot complete.") # Marker


#     def evaluate_model(self, test_data_path=None, test_temperatures=[22, 28, 33, 38]):
#         """Evaluate model performance"""
#         print("Evaluating model...") # Marker
#         # If test data provided, evaluate on it
#         if test_data_path:
#             X_test, y_test, _, _ = self.prepare_data(test_data_path)
#             test_pred = self.model.predict(tf.cast(X_test, tf.float32), verbose=0)
#             test_loss = tf.reduce_mean(tf.square(y_test - test_pred)).numpy()
#             print(f"Test Loss: {test_loss:.6f}")

#         # Generate predictions for different temperatures
#         plt.figure(figsize=(15, 10))

#         for i, T_boundary in enumerate(test_temperatures):
#             plt.subplot(2, 2, i+1)

#             # Generate time array
#             time_array = np.linspace(0, 1000, 200)

#             # Predict melt fraction
#             melt_pred = self.predict(T_boundary, time_array)

#             # Plot
#             plt.plot(time_array, melt_pred, 'b-', linewidth=2,
#                     label=f'PINN Prediction (T={T_boundary}°C)')

#             plt.xlabel('Time (s)')
#             plt.ylabel('Melt Fraction')
#             plt.title(f'Boundary Temperature = {T_boundary}°C')
#             plt.grid(True, alpha=0.3)
#             plt.legend()
#             plt.ylim(0, 1)

#         plt.tight_layout()
#         plt.savefig('pinn_predictions.png', dpi=300, bbox_inches='tight')
#         plt.show()
#         print("Model evaluation complete.") # Marker

#     def save_model(self, filepath):
#         """Save the trained model"""
#         print(f"Saving model to {filepath}...") # Marker
#         self.model.save(filepath)

#         # Save scalers
#         import joblib
#         joblib.dump(self.scaler_input, filepath + '_scaler_input.pkl')
#         joblib.dump(self.scaler_output, filepath + '_scaler_output.pkl')

#         print(f"Model saved to {filepath}") # Marker

#     def load_model(self, filepath):
#         """Load a trained model"""
#         print(f"Loading model from {filepath}...") # Marker
#         self.model.load_model(filepath)

#         # Load scalers
#         import joblib
#         self.scaler_input = joblib.load(filepath + '_scaler_input.pkl')
#         self.scaler_output = joblib.load(filepath + '_scaler_output.pkl')

#         print(f"Model loaded from {filepath}") # Marker



# def train_pinn_model(data_path='pcm_training_data/combined_training_data.csv'):
#     """Main function to train PINN model"""
#     print("=== Training PINN Model for Phase Change Material ===\n")

#     # Initialize PINN
#     pinn = PCM_PINN(
#         hidden_layers=[64, 64, 64], # Simplified hidden layers
#         activation='tanh',
#         learning_rate=0.001,
#         T_solidus=4.0,
#         T_liquidus=5.0
#     )

#     # print("Model characteristics")
#     # print(pinn.model.summary())


#     # Train model
#     history = pinn.train(
#         data_path=data_path,
#         epochs=10, # Reduced epochs for quicker training
#         batch_size=32,
#         validation_split=0.2,
#         physics_weight=0.1,
#         verbose=1
#     )

#     # Plot training history
#     pinn.plot_training_history()

#     # Evaluate model
#     pinn.evaluate_model(test_temperatures=[22, 28, 33, 38, 42])

#     # Save model
#     pinn.save_model('trained_pcm_pinn_model_simple') # Changed filename to indicate simplicity

#     return pinn


# # Example usage and comparison
# def compare_fem_and_pinn():
#     """Compare FEM simulation with PINN predictions"""
#     print("Starting FEM and PINN comparison...") # Marker
#     # Load training data to get a trained PINN (assuming it exists)
#     try:
#         pinn = PCM_PINN()
#         pinn.load_model('trained_pcm_pinn_model_simple') # Load simplified model

#         # Test temperatures
#         test_temperatures = [25, 35, 45]

#         plt.figure(figsize=(15, 5))

#         for i, T_boundary in enumerate(test_temperatures):
#             plt.subplot(1, 3, i+1)

#             # FEM simulation
#             from pcm_fem_simulation import PCMSimulation
#             sim = PCMSimulation()
#             print(f"Running FEM simulation for T_boundary = {T_boundary}°C...") # Marker
#             time_fem, melt_fem = sim.solve_heat_equation(T_boundary, max_time=1000)
#             print(f"FEM simulation for T_boundary = {T_boundary}°C complete.") # Marker

#             # PINN prediction
#             time_pinn = np.linspace(0, 1000, 200)
#             print(f"Running PINN prediction for T_boundary = {T_boundary}°C...") # Marker
#             melt_pinn = pinn.predict(T_boundary, time_pinn)
#             print(f"PINN prediction for T_boundary = {T_boundary}°C complete.") # Marker

#             # Plot comparison
#             plt.plot(time_fem, melt_fem, 'ro-', label='FEM', alpha=0.7)
#             plt.plot(time_pinn, melt_pinn, 'b-', label='PINN', linewidth=2)

#             plt.xlabel('Time (s)')
#             plt.ylabel('Melt Fraction')
#             plt.title(f'T = {T_boundary}°C')
#             plt.legend()
#             plt.grid(True, alpha=0.3)

#         plt.tight_layout()
#         plt.savefig('fem_vs_pinn_comparison_simple.png', dpi=300, bbox_inches='tight') # Changed filename
#         plt.show()
#         print("FEM and PINN comparison plot complete.") # Marker

#     except Exception as e:
#         print(f"Could not load trained model: {e}")
#         print("Please train the model first using train_pinn_model()")


# if __name__ == "__main__":
#     # Check if training data exists
#     if os.path.exists('pcm_training_data/combined_training_data.csv'):
#         print("Training data found. Training PINN model...")
#         trained_pinn = train_pinn_model()

#         # Compare with FEM
#         print("\nComparing FEM and PINN predictions...")
#         compare_fem_and_pinn()
#     else:
#         print("Training data not found. Please run the FEM simulation first to generate training data.")
#         print("Run: python pcm_fem_simulation.py")
