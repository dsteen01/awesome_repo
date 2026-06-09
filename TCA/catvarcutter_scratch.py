import matplotlib.pyplot as plt
import numpy as np

# Data for the x-axis (countries)
countries = ["US", "China", "Japan", "South Korea"]

# Generate 10 random numbers for each country
random_numbers = np.random.randint(10, 101, size=(len(countries), 10))

# Create a binned scatter plot
plt.figure(figsize=(10, 6))

# Plot each country's random numbers
for i, country in enumerate(countries):
    plt.scatter([country] * 10, random_numbers[i], s=100, label=country, alpha=0.7)
    # Calculate quartiles for each country
    q1 = np.percentile(random_numbers, 25, axis=1)
    median = np.percentile(random_numbers, 50, axis=1)
    q3 = np.percentile(random_numbers, 75, axis=1)

    # Create a box and whisker plot
    plt.boxplot(random_numbers, positions=np.arange(len(countries)), widths=0.6, patch_artist=True,
                boxprops={'facecolor': 'lightblue', 'alpha': 0.7},
                medianprops={'color': 'red'})

# Add labels and title
plt.xlabel("Countries")
plt.ylabel("Random Numbers")
plt.title("Binned Scatter Plot with Box and Whisker Plots")

# Show legend
plt.legend()

# Show the plot
plt.grid(axis="y")
plt.tight_layout()
plt.show()