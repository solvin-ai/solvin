// app/layout.js

import './globals.css'; // Make sure this path is correct!
import Header from '../components/Header'; // Adjust path if needed

export const metadata = {
  title: 'Your App Title',
  description: 'App description here',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head />
      <body className="min-h-screen bg-gray-100">
        <Header />
        <main>{children}</main>
      </body>
    </html>
  );
}
