/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html", // Сканировать HTML файлы в папке templates
    "./static/src/**/*.js", // Если будете добавлять JS для UI
  ],
  safelist: [
    'bg-red-100',
    'bg-blue-100',
    'bg-green-100',
    'bg-amber-100',
    'text-red-600',
    'text-blue-600',
    'text-green-600',
    'text-amber-600'
  ],
  theme: {
    extend: {
      colors: {
        primary: { // Используем палитру Tailwind для генерации оттенков или задаем явно
          50: '#eef2ff', // Примерные оттенки, можно настроить
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#0891b2', // Основной сине-бирюзовый (cyan-600 в стандартной палитре)
          600: '#0e7490', // cyan-700
          700: '#155e75', // cyan-800
          800: '#164e63', // cyan-900
          900: '#1e3a8a', // Ближе к индиго/темно-синему для глубоких теней
        },
        secondary: { // Для бирюзового акцента
             50: '#f0fdfa',
            100: '#ccfbf1',
            200: '#99f6e4',
            300: '#5eead4',
            400: '#2dd4bf',
            500: '#14b8a6', // Акцентный бирюзовый (teal-500)
            600: '#0d9488', // teal-600
            700: '#0f766e', // teal-700
            800: '#115e59', // teal-800
            900: '#134e4a', // teal-900
        },
        dark: '#0f172a', // slate-900
        // Добавим стандартные цвета для удобства
        gray: require('tailwindcss/colors').gray,
        blue: require('tailwindcss/colors').blue,
        red: require('tailwindcss/colors').red,
        yellow: require('tailwindcss/colors').yellow,
        green: require('tailwindcss/colors').green,
        cyan: require('tailwindcss/colors').cyan,
        teal: require('tailwindcss/colors').teal,

      },
      fontFamily: {
        // Используем стандартные имена Tailwind, чтобы было проще применять
        sans: ['Inter var', 'system-ui', 'sans-serif'], // Основной шрифт
        display: ['Lexend', 'sans-serif'], // Акцентный шрифт
      },
      animation: {
        'gradient': 'gradient 8s ease infinite',
        'float': 'float 6s ease-in-out infinite',
        // Добавим анимацию для появления элементов
        'fade-in': 'fade-in 0.5s ease-out forwards',
        'slide-up': 'slide-up 0.7s cubic-bezier(0.22, 1, 0.36, 1) forwards',
      },
      keyframes: {
        gradient: {
          '0%, 100%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' }, // Уменьшил амплитуду
        },
        'fade-in': {
             '0%': { opacity: '0' },
             '100%': { opacity: '1' },
        },
        'slide-up': {
             '0%': { opacity: '0', transform: 'translateY(30px)' },
             '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      backgroundImage: {
        'grid-pattern': 'linear-gradient(to right, rgba(14, 116, 144, 0.1) 1px, transparent 1px), linear-gradient(to bottom, rgba(14, 116, 144, 0.1) 1px, transparent 1px)',
         // Добавим градиенты из дизайна
         'hero-gradient': 'radial-gradient(circle at top left, theme("colors.primary.100") 0%, theme("colors.white") 40%)',
         'card-gradient': 'linear-gradient(to bottom right, theme("colors.cyan.500"), theme("colors.teal.500"))',
      },
      backgroundSize: {
        'grid-size': '30px 30px', // Уменьшим размер сетки
      },
      boxShadow: {
        'glow-primary': '0 0 25px -5px theme("colors.primary.500/30")',
        'glow-secondary': '0 0 25px -5px theme("colors.secondary.500/30")'
      }
    },
  },
  plugins: [require('@tailwindcss/forms')], // Плагин для стилизации форм
} 