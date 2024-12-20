# -*- coding: utf-8 -*-
"""Federatedlearning.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1IlPhqUOUffZBOcxjXkCCIrXAu7PR2vBM
"""

!pip install torch scikit-learn matplotlib pandas numpy

import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import matplotlib.pyplot as plt
from concurrent.futures import ThreadPoolExecutor
import time
import copy

# Loading and processing the dataset
df = pd.read_csv("/content/chronickidneydiseases.csv")
X = df.iloc[:, :-1].values  # All columns except the last one (features)
y = df['RecommendedVisitsPerMonth'].values  # The target variable

label_encoder = LabelEncoder()
y = label_encoder.fit_transform(y)

# Normalize the feature set
scaler = StandardScaler()
X = scaler.fit_transform(X)  # Fitting scaler on the dataset

# Split dataset into training and validation sets
X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)

# Convert to PyTorch tensors
X_train = torch.FloatTensor(X_train)
y_train = torch.LongTensor(y_train)
X_val = torch.FloatTensor(X_val)
y_val = torch.LongTensor(y_val)

# Model Definition
class SimpleNN(nn.Module):
    def __init__(self, input_size, output_size):
        super(SimpleNN, self).__init__()
        self.fc1 = nn.Linear(input_size, 64)
        self.bn1 = nn.BatchNorm1d(64)
        self.fc2 = nn.Linear(64, 32)
        self.bn2 = nn.BatchNorm1d(32)
        self.fc3 = nn.Linear(32, output_size)

    def forward(self, x):
        x = F.relu(self.bn1(self.fc1(x)))
        x = F.relu(self.bn2(self.fc2(x)))
        x = self.fc3(x)
        return x

# Federated Learning Client Class
class Client:
    def __init__(self, client_id, dataset, device):
        self.client_id = client_id
        self.dataset = dataset
        self.device = device

    def train(self, global_model, epochs, lr, batch_size):
        model = copy.deepcopy(global_model)
        model.to(self.device)
        model.train()
        optimizer = torch.optim.Adam(model.parameters(), lr=lr)
        train_loader = torch.utils.data.DataLoader(self.dataset, batch_size=batch_size, shuffle=True)

        for epoch in range(epochs):
            running_loss = 0.0
            for data, target in train_loader:
                data, target = data.to(self.device), target.to(self.device)
                optimizer.zero_grad()
                output = model(data)
                loss = F.cross_entropy(output, target)
                loss.backward()
                optimizer.step()
                running_loss += loss.item() * data.size(0)
        return model.state_dict()

# Federated Averaging Function
def federated_average(client_weights):
    avg_weights = copy.deepcopy(client_weights[0])
    for key in avg_weights.keys():
        stacked = torch.stack([weights[key] for weights in client_weights])
        if stacked.dtype in [torch.float32, torch.float64]:
            avg_weights[key] = stacked.mean(dim=0)
        else:
            avg_weights[key] = stacked.float().mean(dim=0).to(stacked.dtype)
    return avg_weights

# Training setup
num_clients = 4
epochs = 5
lr = 0.001
batch_size = 1000
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Split dataset among clients
base_size = len(X_train) // num_clients
remainder = len(X_train) % num_clients
split_sizes = [base_size + 1 if i < remainder else base_size for i in range(num_clients)]
client_datasets = torch.utils.data.random_split(list(zip(X_train, y_train)), split_sizes)

# Initialize clients
clients = [Client(client_id=i, dataset=client_datasets[i], device=device) for i in range(num_clients)]

# Initialize global model
input_size = X_train.shape[1]
output_size = len(set(y))
global_model = SimpleNN(input_size, output_size).to(device)

# Initialize tracking variables
validation_accuracies_serial = []
validation_accuracies_parallel = []

# Serial Federated Learning
start_serial = time.time()
for round_num in range(epochs):
    print(f"--- Serial Round {round_num + 1} ---")
    client_weights = []
    round_start = time.time()
    for idx, client in enumerate(clients):
        weights = client.train(global_model, epochs=1, lr=lr, batch_size=batch_size)
        client_weights.append(weights)

    # Federated averaging to update the global model
    global_weights = federated_average(client_weights)
    global_model.load_state_dict(global_weights)

    # Evaluate global model
    global_model.eval()
    correct = 0
    total = 0
    val_loader = torch.utils.data.DataLoader(list(zip(X_val, y_val)), batch_size=batch_size, shuffle=False)

    with torch.no_grad():
        for data, target in val_loader:
            data, target = data.to(device), target.to(device)
            outputs = global_model(data)
            _, predicted = torch.max(outputs.data, 1)
            total += target.size(0)
            correct += (predicted == target).sum().item()

    accuracy = 100 * correct / total
    validation_accuracies_serial.append(accuracy)
    round_end = time.time()
    round_time = round_end - round_start
    print(f"Validation Accuracy after Round {round_num + 1}: {accuracy:.2f}%")
    print(f"Time taken for Serial Round {round_num + 1}: {round_time:.2f} seconds")

end_serial = time.time()
serial_time = end_serial - start_serial
print(f"Total Time Taken for Serial Processing: {serial_time:.2f} seconds\n")

# Parallel Federated Learning
start_parallel = time.time()

def train_client_parallel(client):
    return client.train(global_model, epochs=1, lr=lr, batch_size=batch_size)

for round_num in range(epochs):
    print(f"--- Parallel Round {round_num + 1} ---")
    round_start = time.time()
    with ThreadPoolExecutor(max_workers=num_clients) as executor:
        client_weights = list(executor.map(train_client_parallel, clients))

    # Federated averaging to update the global model
    global_weights = federated_average(client_weights)
    global_model.load_state_dict(global_weights)

    # Evaluate global model
    global_model.eval()
    correct = 0
    total = 0
    val_loader = torch.utils.data.DataLoader(list(zip(X_val, y_val)), batch_size=batch_size, shuffle=False)

    with torch.no_grad():
        for data, target in val_loader:
            data, target = data.to(device), target.to(device)
            outputs = global_model(data)
            _, predicted = torch.max(outputs.data, 1)
            total += target.size(0)
            correct += (predicted == target).sum().item()

    accuracy = 100 * correct / total
    validation_accuracies_parallel.append(accuracy)
    round_end = time.time()
    round_time = round_end - round_start
    print(f"Validation Accuracy after Round {round_num + 1}: {accuracy:.2f}%")
    print(f"Time taken for Parallel Round {round_num + 1}: {round_time:.2f} seconds")

end_parallel = time.time()
parallel_time = end_parallel - start_parallel
print(f"Total Time Taken for Parallel Processing: {parallel_time:.2f} seconds\n")

# Calculate speedup and efficiency
speedup = serial_time / parallel_time
efficiency = speedup / num_clients

# Plotting
plt.figure(figsize=(15, 8))

# Plot 1: Execution Times
plt.subplot(2, 2, 1)
execution_times = {'Serial': serial_time, 'Parallel': parallel_time}
plt.bar(execution_times.keys(), execution_times.values(), color=['orange', 'blue'])
plt.xlabel('Execution Type')
plt.ylabel('Time (seconds)')
plt.title('Execution Time: Serial vs Parallel')
plt.grid(True)

# Plot 2: Validation Accuracy
plt.subplot(2, 2, 2)
plt.plot(range(1, epochs + 1), validation_accuracies_serial, marker='o', label='Serial')
plt.plot(range(1, epochs + 1), validation_accuracies_parallel, marker='s', label='Parallel')
plt.xlabel('Rounds')
plt.ylabel('Validation Accuracy (%)')
plt.title('Validation Accuracy: Serial vs Parallel')
plt.legend()
plt.grid(True)

plt.tight_layout()
plt.show()

# Output the final speedup and efficiency
print(f"Speedup: {speedup:.2f}")
print(f"Efficiency: {efficiency:.2f}")


# Function to take user input, preprocess it, and predict
def predict(global_model, scaler, label_encoder):
    global_model.eval()  # Set the model to evaluation mode

    print("\nEnter the following details to predict recommended visits per month:")
    try:
        age = float(input("Age: "))
        bmi = float(input("BMI: "))
        systolic_bp = float(input("SystolicBP: "))
        serum_creatinine = float(input("SerumCreatinine: "))
        gfr = float(input("GFR: "))
        medication_adherence = float(input("MedicationAdherence: "))

        # Creating a feature vector from user input
        user_data = np.array([[age, bmi, systolic_bp, serum_creatinine, gfr, medication_adherence]])
        user_data_scaled = scaler.transform(user_data)  # Normalize the input data
        user_data_tensor = torch.FloatTensor(user_data_scaled).to(device)

        with torch.no_grad():
            outputs = global_model(user_data_tensor)
            _, predicted = torch.max(outputs.data, 1)

        predicted_class = label_encoder.inverse_transform([predicted.item()])
        print(f"\nPredicted Recommended Visits Per Month: {predicted_class[0]}")

    except ValueError:
        print("Invalid input! Please provide numerical values for all fields.")

# Prediction
if __name__ == "__main__":
    print("\nPrediction Mode:")
    predict(global_model, scaler, label_encoder)