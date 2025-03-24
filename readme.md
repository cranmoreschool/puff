[![New-Project.png](https://i.postimg.cc/x1P7G56K/New-Project.png)](https://postimg.cc/5X6nbBd0)

# AirTester (Puff)

We have an Air Quality Sensor that measures the particulate matter (PM for short) in the air. It can spike when doing things such as:
* smoking
* burning
* vehicle exhaust or outdoor pollutants

This can be bad for you in the short-term, leading to things like eye irritation and asthma.  
In the long-term, it can cause lung cancer and heart disease.  
We don't claim to cure your lung cancer, but it is a great cost-effective way to be mindful about the hazards around you and take steps to limit your exposure. PM2.5 particles are so small they can penetrate deep into the lungs, so much that they have been labelled as the "silent killer". We all like breathing, so this is a win-win solution for everyone, especially people exposed to pollution and the elderly. In places like schools, sensors could be deployed in classrooms to monitor air quality and make sure particulate matter levels stay low, reducing things like asthma triggers in small children with sensitive lungs. As well as this, clean air is proven to reduce fatigue, improve focus, and minimize health-related absences.

Our code is well made, with effectiveness and user simplicity our No.1 priority. We decided to use Python for its syntax and simplicity to set up. C was also a thought that we had, but compilation and interaction with other modules of our code was too slow. As a result, we lost some efficiency from the low-level code that C offers, but gained a lot of user simplicity. We used a web application as TailwindCSS made it easier to refine the different components and also make it look nicer for our audience while staying bloat-free and responsive. We stored the database in a database called "sensor_data.db", to keep track of the history and let Puff (our NLP assistant) access it. We used Flask for our web application and simple math to read and parse data from the SDS011 sensor using a built-in function that returns the number of elements (length) in an iterator/object passed to the function, also known as `len()`. Puff is an NLP Agent Chatbot, so you type to it in a message area like iMessage (Natural Language Processing) who, instead of using ChatGPT or other API functions, processes the words locally and matches them, like an Alexa. When you ask your Alexa for the weather, it interprets the words "weather" and "today" to understand what you said and provide the answer quicker than GPT. Some of our phrases are "current air quality" and "how's the air", as you can't expect the user to only say one sentence. To make it easier for the user, Puff shows a blue light (like Alexa).

Our setup is very streamlined, needing only three commands to set up the air sensor. First, cd (change directory) into the folder after installation. We did:

```bash
cd puff
```

After this, run your installer using the bash command:

```bash
bash installer.sh
```

Finally, run your Python code:

```bash
python main.py
```

## Credits:
- **Ismael P** for Project Managing and Development
- **Seb S** for Head Researcher and making our name
- **Monty** for Product Design
- **Conor** for Product Research
